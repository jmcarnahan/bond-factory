"""Which building is measured (plan 3.3): the parcel that holds the roof point, the outline on it, an outline by id,
and the answer carried into the envelope (``model.source.building``, ``model.quality.parcel_match``). Synthetic parcels."""

import json
from types import SimpleNamespace

import pytest
from conftest import FIXTURES

from roof_measure import footprint, footprint_county, pipeline, pipeline_stages
from roof_measure.footprint_types import FootprintError, FootprintUnavailable
from roof_measure.geocode import Address
from roof_measure.library import measure

LAT, LNG, D = 34.0, -118.0, 0.0001  # D is about 11 m
ADDR = Address("100 Example Ave", "Sampletown", "CA", "90000")
BLOCKS = FIXTURES / "site1_blocks.json"


def ring(lat0, lng0, dlat, dlng):
    return [(lng0, lat0), (lng0 + dlng, lat0), (lng0 + dlng, lat0 + dlat), (lng0, lat0 + dlat), (lng0, lat0)]


def parcel(house, west, ain, street="EXAMPLE AVE"):
    """A 5 x 5 D square whose west edge is ``west`` D east of LNG."""
    return {"type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring(LAT, LNG + west * D, 5 * D, 5 * D)]},
            "properties": {"SitusHouseNo": house, "SitusStreet": street, "SitusDirection": "",
                           "SitusAddress": f"{house} {street}", "AIN": ain}}


def outline(bld, south, west, size, area=1000.0):
    return {"type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring(LAT + south * D, LNG + west * D, size * D, size * D)]},
            "properties": {"BLD_ID": bld, "OBJECTID": 900 + len(bld), "HEIGHT": 12.0, "AREA": area}}


A = parcel("100", 0, "P-A")
B = parcel("102", 5, "P-B")  # the neighbour to the east


def county(net, parcels, buildings):
    net.routes["LACounty_Parcel"] = {"features": parcels}
    net.routes["Countywide_Building_Outlines"] = {"features": buildings}


def pt(south, west):
    return LAT + south * D, LNG + west * D


# ---- (a) the parcel and the outline that hold the point
def test_a_pin_inside_the_neighbour_parcel_beats_the_text_match():
    best, match = footprint_county.pick_parcel([A, B], *pt(2, 7), ADDR, point_given=True)
    assert best["properties"]["AIN"] == "P-B" and match == "nearest"  # number 102 is not 100: not "exact"


def test_without_a_pin_the_text_still_wins():
    best, match = footprint_county.pick_parcel([A, B], *pt(2, 7), ADDR)
    assert best["properties"]["AIN"] == "P-A" and match == "exact"


def test_exact_needs_number_and_street_even_with_a_pin():
    _, match = footprint_county.pick_parcel([A, B], *pt(2, 2), ADDR, point_given=True)
    assert match == "exact"
    wrong_street = parcel("100", 0, "P-C", street="OTHER ST")
    _, match = footprint_county.pick_parcel([wrong_street], *pt(2, 2), ADDR, point_given=True)
    assert match == "street"  # the number matches, the street does not


def test_a_pin_in_no_parcel_falls_back_to_the_text_rule_but_is_never_exact():
    best, match = footprint_county.pick_parcel([A, B], *pt(2, -3), ADDR, point_given=True)
    assert best["properties"]["AIN"] == "P-A" and match == "street"  # the text matches, the pin is on no parcel
    assert footprint_county.pick_parcel([A, B], *pt(2, -3), ADDR)[1] == "exact"  # without a pin the rule is as before


def test_a_pin_in_no_parcel_warns_through_the_chain(net):
    county(net, [A], [outline("H", 1, 1, 2)])
    fp = footprint.fetch_footprint(*pt(2, -3), ADDR, point_given=True)
    assert fp.match == "street" and "parcel_street_match" in fp.warning_codes


def test_the_outline_containing_the_pin_wins_over_the_largest(net):
    big, small = outline("BIG", 0.2, 0.2, 3, 5000.0), outline("SMALL", 3.8, 3.8, 1, 400.0)
    county(net, [A], [big, small])
    assert footprint.fetch_footprint(*pt(4.2, 4.2), ADDR).id == "BIG"  # no pin: the largest
    fp = footprint.fetch_footprint(*pt(4.2, 4.2), ADDR, point_given=True)
    assert fp.id == "SMALL" and fp.match == "exact" and fp.parcel_id == "P-A"
    assert [i["id"] for i in fp.other_info] == ["BIG"]


def test_a_pin_between_outlines_takes_the_nearest(net):
    near, far = outline("NEAR", 0.5, 0.5, 1), outline("FAR", 0.5, 3.5, 1)
    county(net, [A], [far, near])
    assert footprint.fetch_footprint(*pt(2.5, 2.0), ADDR, point_given=True).id == "NEAR"
    assert footprint.fetch_footprint(*pt(2.5, 3.3), ADDR, point_given=True).id == "FAR"


def test_a_pin_in_the_neighbour_parcel_measures_that_parcels_building(net):
    mine, theirs = outline("MINE", 1, 1, 2), outline("THEIRS", 1, 6, 2)
    # the one outline query asks for the parcel grown by 60 m (0.5.1): a spatial query answers with both outlines, and
    # the parcel rule (overlap with the chosen parcel) still picks the neighbour's
    net.routes["LACounty_Parcel"] = {"features": [A, B]}
    net.routes["Countywide_Building_Outlines"] = {"features": [mine, theirs]}
    fp = footprint.fetch_footprint(*pt(2, 7), ADDR, point_given=True)
    assert fp.id == "THEIRS" and fp.parcel_id == "P-B" and fp.match == "nearest"
    assert "parcel_street_match" in fp.warning_codes  # the caller still hears that the text did not match
    assert [(n["outline_id"], n["on_matched_parcel"]) for n in fp.nearby] == [("MINE", False)]


# ---- (b) an outline by id
def lookup(*rows):
    def route(url, kw):
        if "where" in kw.get("params", {}):
            wanted = kw["params"]["where"]
            return {"features": [r for r in rows if f"'{r['properties']['BLD_ID']}'" in wanted]}
        return {"features": list(rows)}  # the parcel's outline query
    return route


def test_an_outline_id_is_used_exactly(net):
    mine, other = outline("MINE", 1, 1, 2, 800.0), outline("OTHER", 3, 3, 2, 3000.0)
    net.routes["LACounty_Parcel"] = {"features": [A, B]}
    net.routes["Countywide_Building_Outlines"] = lookup(mine, other)
    fp = footprint.fetch_footprint(LAT - 9 * D, LNG - 9 * D, ADDR, building_outline_id="MINE")  # the point is ignored
    assert fp.id == "MINE" and fp.match == "given" and fp.parcel_id == "P-A"
    assert fp.warnings == []  # a choice is not a weak match
    assert [i["id"] for i in fp.other_info] == ["OTHER"] and len(fp.other_buildings) == 1  # the lot is kept
    info = pipeline_stages._footprint_info(fp)
    assert info["match"] == "given" and info["building"]["chosen_by"] == "user"
    assert info["building"]["outline_id"] == "MINE" and info["building"]["parcel_id"] == "P-A"


def test_an_unknown_outline_id_is_an_error_and_never_another_building(net, monkeypatch):
    net.routes["LACounty_Parcel"] = {"features": [A]}
    net.routes["Countywide_Building_Outlines"] = lookup(outline("MINE", 1, 1, 2))
    monkeypatch.setattr(footprint, "fetch_osm", lambda *a, **k: pytest.fail("the chain must not go on to OSM"))
    with pytest.raises(FootprintError, match="not found"):
        footprint.fetch_footprint(LAT, LNG, ADDR, building_outline_id="NOPE")
    with pytest.raises(FootprintError):
        footprint.fetch_footprint(LAT, LNG, ADDR, building_outline_id="x' OR '1'='1")  # never reaches the layer
    assert not any("OR '1'" in str(kw.get("params")) for _, kw in net.calls)


def test_an_unreachable_county_layer_is_an_outage_for_an_outline_id(net):
    import requests

    net.routes["Countywide_Building_Outlines"] = requests.ConnectionError("down")
    with pytest.raises(FootprintUnavailable):
        footprint.fetch_footprint(LAT, LNG, ADDR, building_outline_id="MINE")


def test_measure_accepts_the_outline_id_and_unknown_id_is_no_footprint(tmp_path, net):
    from roof_measure.library import MeasureError

    net.routes["LACounty_Parcel"] = {"features": [A]}
    net.routes["Countywide_Building_Outlines"] = {"features": []}
    with pytest.raises(MeasureError) as e:
        measure("", lat=LAT, lng=LNG, method="lidar_skeleton", verify=False, cache_dir=tmp_path / "c", isolate=False,
                building_outline_id="NOPE")
    assert e.value.code == "no_footprint"


# ---- (c) the answer in the envelope
def blocks_with(tmp_path, fpinfo):
    doc = json.loads(BLOCKS.read_text())
    doc["extra"] = {**doc.get("extra", {}), "_fp": fpinfo}
    path = tmp_path / "blocks.json"
    path.write_text(json.dumps(doc))
    return path


def test_the_envelope_carries_the_building_and_the_parcel_match(tmp_path):
    building = {"parcel_id": "P-A", "outline_id": "MINE", "outline_centroid": [LAT + D, LNG - D], "chosen_by": "auto"}
    path = blocks_with(tmp_path, {"source": "lariac", "warnings": [], "codes": [], "other_buildings": 0,
                                  "match": "street", "building": building})
    env = pipeline.run_pipeline("x", tmp_path / "out", "lidar_skeleton", blocks_path=path, verify=False,
                                render=False).envelope
    assert env["model"]["source"]["building"] == building
    assert env["model"]["quality"]["parcel_match"] == "street"


def test_old_blocks_files_have_neither_key(tmp_path):
    env = pipeline.run_pipeline("x", tmp_path / "out", "lidar_skeleton", blocks_path=BLOCKS, verify=False,
                                render=False).envelope
    assert "building" not in env["model"]["source"] and "parcel_match" not in env["model"].get("quality", {})


def test_a_non_county_footprint_has_a_building_but_no_parcel_match():
    from shapely.geometry import box

    fp = SimpleNamespace(source="osm", warnings=[], warning_codes=[], other_buildings=[], transient=False,
                         match="exact", parcel_id=None, id="77", polygon_wgs84=box(LNG, LAT, LNG + D, LAT + D))
    info = pipeline_stages._footprint_info(fp)
    assert info["match"] is None
    assert info["building"] == {"parcel_id": None, "outline_id": "77", "outline_centroid": [round(LAT + D / 2, 7), round(LNG + D / 2, 7)],
                                "chosen_by": "auto"}


def test_an_outline_id_chooses_the_parcel_under_the_outline_not_the_text(net):
    theirs = outline("THEIRS", 1, 6, 2)  # on parcel B; the address text names parcel A (number 100)
    net.routes["LACounty_Parcel"] = {"features": [A, B]}
    net.routes["Countywide_Building_Outlines"] = lookup(theirs)
    fp = footprint.fetch_footprint(LAT, LNG, ADDR, building_outline_id="THEIRS")
    assert fp.id == "THEIRS" and fp.parcel_id == "P-B" and fp.match == "given"


def test_an_outline_on_no_parcel_gets_an_accurate_error(net):
    far = outline("FAR", 30, 30, 2)
    net.routes["LACounty_Parcel"] = {"features": [A]}
    net.routes["Countywide_Building_Outlines"] = lookup(far)
    with pytest.raises(FootprintError, match="not on any parcel"):
        footprint.fetch_footprint(LAT, LNG, ADDR, building_outline_id="FAR")


def test_an_outline_without_an_id_gets_a_stable_geometry_id_never_none(net):
    bare = outline("X", 1, 1, 2)
    bare["properties"] = {"HEIGHT": 12.0, "AREA": 900.0}
    county(net, [A], [bare])
    one = footprint.fetch_footprint(LAT, LNG, ADDR)
    two = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert one.id.startswith("geo-") and one.id == two.id and "None" not in one.id
    assert any("no id" in w for w in one.warnings)


def test_the_outline_centroid_lies_inside_an_l_shaped_outline():
    from shapely.geometry import Polygon

    ell = Polygon([(LNG, LAT), (LNG + 10 * D, LAT), (LNG + 10 * D, LAT + D), (LNG + D, LAT + D),
                   (LNG + D, LAT + 10 * D), (LNG, LAT + 10 * D)])
    assert not ell.contains(ell.centroid)  # the centroid of this L is in the notch
    fp = SimpleNamespace(source="lariac", warnings=[], warning_codes=[], other_buildings=[], transient=False,
                         match="exact", parcel_id="P", id="L", polygon_wgs84=ell)
    lat, lng = pipeline_stages._footprint_info(fp)["building"]["outline_centroid"]
    from shapely.geometry import Point

    assert ell.contains(Point(lng, lat))
