"""``nearby_buildings`` (0.5.1): the county outlines within 60 m of the lookup point other than the measured one, from the
ONE outline query the footprint step already makes. Synthetic parcels (D is about 11 m)."""

import json

from test_building_selection import ADDR, LAT, LNG, A, B, D, county, outline, pt

from roof_measure import footprint, pipeline_stages


def test_the_outline_query_is_one_request_and_covers_the_parcel_plus_the_radius(net):
    county(net, [A], [outline("MINE", 1, 1, 2)])
    footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    asked = [kw for url, kw in net.calls if "Countywide_Building_Outlines" in url]
    assert len(asked) == 1  # no second round trip for the neighbours
    ring = json.loads(asked[0]["data"]["geometry"])["rings"][0]
    xs, ys = [x for x, _ in ring], [y for _, y in ring]
    assert min(xs) < LNG - 4 * D and max(xs) > LNG + 9 * D  # the 5 D wide parcel (55 m) grown by 60 m (5 D) each way
    assert min(ys) < LAT - 4 * D and max(ys) > LAT + 9 * D


def test_nearby_lists_the_other_outlines_within_60_m_nearest_first(net):
    mine = outline("MINE", 1, 1, 2, 900.0)
    near = outline("NEAR", 3, 3, 1, 400.0)  # on the parcel, a few metres away
    shed = outline("SHED", 1, 5.5, 1, 120.0)  # beside the parcel's east edge: touches the neighbour's side
    next_door = outline("NEXT", 1, 8, 2, 1500.0)  # on the next parcel, within 60 m of the pin
    far = outline("FAR", 1, 30, 2, 1500.0)  # more than 60 m away
    county(net, [A], [far, next_door, shed, near, mine])
    fp = footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    assert fp.id == "MINE"
    ids = [n["outline_id"] for n in fp.nearby]
    assert "FAR" not in ids and "MINE" not in ids
    assert ids[0] == "NEAR" and ids == sorted(ids, key=lambda i: next(n["distance_m"] for n in fp.nearby if n["outline_id"] == i))
    by = {n["outline_id"]: n for n in fp.nearby}
    assert set(by["NEAR"]) == {"outline_id", "area_sqft", "distance_m", "on_matched_parcel"}
    assert by["NEAR"]["on_matched_parcel"] is True and by["NEAR"]["area_sqft"] == 400.0
    assert by["NEXT"]["on_matched_parcel"] is False and 0 < by["NEXT"]["distance_m"] <= 60.0


def test_nearby_is_capped_at_eight_and_leaves_out_outlines_without_an_id(net):
    mine = outline("MINE", 1, 1, 2)
    many = [outline(f"N{i}", 0.2 + 0.4 * i, 3.2, 0.3) for i in range(11)]
    nameless = outline("X", 3.0, 0.5, 0.3)
    del nameless["properties"]["BLD_ID"]
    del nameless["properties"]["OBJECTID"]
    county(net, [A], [mine, nameless, *many])
    fp = footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    assert len(fp.nearby) == 8
    assert all(n["outline_id"].startswith("N") for n in fp.nearby)  # nothing that a later request could not name


def test_a_lone_building_has_an_empty_list_and_the_info_carries_it(net):
    county(net, [A], [outline("MINE", 1, 1, 2)])
    fp = footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    assert fp.nearby == []
    assert pipeline_stages._footprint_info(fp)["nearby_buildings"] == []


def test_the_neighbours_parcel_building_is_nearby_not_measured(net):
    county(net, [A, B], [outline("MINE", 1, 1, 2), outline("THEIRS", 1, 6, 2)])
    fp = footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    assert fp.id == "MINE"
    assert [(n["outline_id"], n["on_matched_parcel"]) for n in fp.nearby] == [("THEIRS", False)]


def test_a_nearby_outline_id_can_be_chosen_in_the_next_request(net):
    county(net, [A], [outline("MINE", 1, 1, 2), outline("NEAR", 3, 3, 1, 400.0)])
    fp = footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    chosen = fp.nearby[0]["outline_id"]
    again = footprint.fetch_footprint(*pt(2, 2), ADDR, building_outline_id=chosen)
    assert again.id == chosen == "NEAR" and again.match == "given"


def test_a_record_cap_falls_back_to_the_parcel_query_and_lists_no_neighbours(net):
    def route(url, kw):
        rings = json.loads(kw["data"]["geometry"])["rings"][0]
        wide = max(x for x, _ in rings) > LNG + 8 * D
        rows = [outline("MINE", 1, 1, 2), outline("NEAR", 3, 3, 1)]
        return {"features": rows, "exceededTransferLimit": True} if wide else {"features": rows}

    net.routes["LACounty_Parcel"] = {"features": [A]}
    net.routes["Countywide_Building_Outlines"] = route
    fp = footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    assert fp.nearby == [] and fp.id == "MINE"
    assert any("not listed" in w for w in fp.warnings) and "other" in fp.warning_codes
    assert len([1 for u, _ in net.calls if "Countywide_Building_Outlines" in u]) == 2


def test_an_outline_that_comes_back_twice_is_listed_once(net):
    county(net, [A], [outline("MINE", 1, 1, 2), outline("NEAR", 3, 3, 1), outline("NEAR", 3, 3, 1)])
    fp = footprint.fetch_footprint(*pt(2, 2), ADDR, point_given=True)
    assert [n["outline_id"] for n in fp.nearby] == ["NEAR"]
