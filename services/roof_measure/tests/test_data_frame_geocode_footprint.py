"""Data layer tests: frame, geocode, footprint, cache. No network: `cache._send` is replaced."""

from __future__ import annotations

import json
import os

import numpy as np
import pytest
from shapely.geometry import shape
from sites import PLACEHOLDER, local_data_path

from roof_measure import cache, footprint, geocode
from roof_measure.frame import FT_PER_M, Frame, utm_epsg_for

_skip = pytest.mark.skipif(not os.environ.get("ROOF_MEASURE_NETWORK"), reason="needs network")


def network(fn):
    """Mark a test as needing the live network; skipped unless ROOF_MEASURE_NETWORK=1."""
    return pytest.mark.network(_skip(fn))


def _load(name: str) -> bytes:
    """Bytes of a local/test-data file; the test is skipped when it is absent."""
    path = local_data_path(name)
    if path is None:
        pytest.skip(f"local/test-data/{name} missing")
    return path.read_bytes()


def _addr(site: dict) -> geocode.Address:
    return geocode.Address(site["line1"], site["city"], site["state"], site["zip"])


def _pt(site: dict) -> tuple[float, float]:
    """(lat, lng) the recorded Census response geocodes the site to."""
    return site["geocode_point"]["lat"], site["geocode_point"]["lon"]


@pytest.fixture
def fake_net(tmp_path, monkeypatch):
    """Isolated cache dir plus a routable fake network; returns the list of URLs requested."""
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path / "cache"))
    calls: list[str] = []
    routes: dict[str, bytes] = {}

    def send(method, url, params, data, headers, timeout):
        calls.append(url)
        for frag, body in routes.items():
            if frag in url:
                return body
        raise AssertionError(f"unexpected request {url}")

    monkeypatch.setattr(cache, "_send", send)
    monkeypatch.setattr(cache.time, "sleep", lambda _s: None)
    calls_routes = type("Net", (), {"calls": calls, "routes": routes})
    return calls_routes


# ---------------------------------------------------------------- frame
def test_utm_zone_from_longitude():
    assert utm_epsg_for(-118.5, 33.5) == 32611
    assert utm_epsg_for(2.35, 48.85) == 32631
    assert utm_epsg_for(151.2, -33.87) == 32756


def test_frame_round_trip_and_origin():
    fp = shape(json.loads(_load("buildings_parcel_site1.geojson"))["features"][0]["geometry"])
    frame, fp_m = Frame.for_footprint(fp)
    assert frame.epsg == 32611
    minx, miny, _, _ = fp_m.bounds
    assert frame.to_ft((minx, miny)) == pytest.approx([0.0, 0.0], abs=1e-9)
    pts = np.array([[minx + 10.0, miny + 5.0], [minx + 40.0, miny + 22.0]])
    ft = frame.to_ft(pts)
    assert ft[0] == pytest.approx([10 * FT_PER_M, 5 * FT_PER_M])
    assert frame.to_m(ft) == pytest.approx(pts)
    assert np.all(frame.to_ft(np.array(fp_m.exterior.coords)) >= -1e-9)
    # origin lat/lng is the SW bbox corner: south-west of the footprint centroid
    c = fp.centroid
    assert frame.origin_lat < c.y and frame.origin_lng < c.x


# ---------------------------------------------------------------- geocode
def test_geocode_parses_recorded_census_response(fake_net, site1):
    fake_net.routes["geocoding.geo.census.gov"] = _load("census_site1.json")
    g = geocode.geocode(f"{site1['line1']}, {site1['city']}, {site1['state']} {site1['zip']}")
    assert g.formatted == site1["formatted"]
    assert g.lat == pytest.approx(site1["geocode_point"]["lat"])
    assert g.lng == pytest.approx(site1["geocode_point"]["lon"])
    assert (g.parts.line1, g.parts.city, g.parts.state, g.parts.zip) == (
        site1["line1"], site1["city"], site1["state"], site1["zip"])


def test_geocode_no_match_has_human_message(fake_net):
    fake_net.routes["geocoding.geo.census.gov"] = json.dumps({"result": {"addressMatches": []}}).encode()
    with pytest.raises(geocode.GeocodeError, match="no match"):
        geocode.geocode("1 Nowhere Rd")


@network
def test_geocode_live(site1):
    assert geocode.geocode(f"{site1['line1']}, {site1['city']}, {site1['state']} {site1['zip']}").parts.zip == site1["zip"]


# ---------------------------------------------------------------- footprint
ADDR = geocode.Address(PLACEHOLDER["line1"], PLACEHOLDER["city"], PLACEHOLDER["state"], PLACEHOLDER["zip"])


def _county_routes(net):
    net.routes["LACounty_Parcel"] = _load("parcels_site1_60m.geojson")
    net.routes["Countywide_Building_Outlines"] = _load("buildings_parcel_site1.geojson")


def test_footprint_picks_target_building_on_matching_parcel(fake_net, site1):
    _county_routes(fake_net)
    fp = footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert fp.provider == "lacounty_lariac_2020"
    assert fp.id == site1["footprint_id"]
    assert fp.parcel_id == site1["parcel_id"]
    assert fp.height_ft == pytest.approx(29.21)
    assert fp.area_sqft == pytest.approx(6901.4, abs=1.0)
    assert len(fp.polygon_wgs84.exterior.coords) - 1 == 46
    assert fp.polygon_wgs84.exterior.is_ccw
    assert fp.other_buildings == []


def test_parcel_choice_uses_address_not_proximity(site1):
    feats = json.loads(_load("parcels_site1_60m.geojson"))["features"]
    # a point in front of the neighbour (nearest parcel is NOT the target) still resolves the target by house number
    npt = site1["parcel_tests"]["near_neighbor_point"]
    best, match = footprint.pick_parcel(feats, npt["lat"], npt["lon"], _addr(site1))
    assert best["properties"]["AIN"] == site1["parcel_id"] and match == "exact"
    near104 = footprint.pick_parcel(feats, npt["lat"], npt["lon"],
                                    geocode.Address(site1["parcel_tests"]["neighbor_line1"], "R", "CA", "1"))
    assert near104[0]["properties"]["SitusHouseNo"] == "104"


def test_parcel_without_house_number_is_flagged_nearest(site1):
    feats = json.loads(_load("parcels_site1_60m.geojson"))["features"]
    tp = site1["parcel_tests"]["truth_point"]
    best, match = footprint.pick_parcel(feats, tp["lat"], tp["lon"],
                                        geocode.Address(site1["parcel_tests"]["missing_line1"], "R", "CA", "1"))
    assert match == "nearest" and best["properties"]["SitusHouseNo"] != "999"


def test_area_sqft_is_in_square_feet():
    poly = shape({"type": "Polygon", "coordinates": [_sq(-118.0, 33.0, 0.0001, 0.0001)]})  # ~9.3 m x 11.1 m
    assert 1000 < footprint._area_sqft(poly) < 1250


def test_footprint_second_call_is_cached(fake_net, site1):
    _county_routes(fake_net)
    footprint.fetch_footprint(*_pt(site1), _addr(site1))
    n = len(fake_net.calls)
    footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert n == 2 and len(fake_net.calls) == n


def test_footprint_falls_back_to_osm(fake_net, site1):
    fake_net.routes["LACounty_Parcel"] = json.dumps({"features": []}).encode()
    fake_net.routes["overpass-api.de"] = _load("overpass_site1.json")
    fp = footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert fp.provider == "osm"
    assert fp.polygon_wgs84.is_valid and fp.area_sqft > 100
    assert fp.parcel_id is None


def test_inexact_address_warns(fake_net, site1):
    _county_routes(fake_net)
    fp = footprint.fetch_footprint(*_pt(site1),
                                   geocode.Address(site1["parcel_tests"]["missing_line1"], site1["city"],
                                                   site1["state"], site1["zip"]))
    assert fp.match != "exact" and any("no exact parcel match" in w for w in fp.warnings)


def _sq(lng0, lat0, dx, dy):
    return [[lng0, lat0], [lng0 + dx, lat0], [lng0 + dx, lat0 + dy], [lng0, lat0 + dy], [lng0, lat0]]


def test_building_chosen_by_overlap_with_parcel_not_size(fake_net, site1):
    """A big neighbour touching the parcel edge must lose to the building that sits on the parcel."""
    parcels = json.loads(_load("parcels_site1_60m.geojson"))
    parcel = next(f for f in parcels["features"] if f["properties"]["AIN"] == site1["parcel_id"])
    ring = parcel["geometry"]["coordinates"][0]
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    x0, x1 = min(p[0] for p in ring), max(p[0] for p in ring)
    inside = {"type": "Feature", "properties": {"BLD_ID": "INSIDE", "AREA": 1500.0},
              "geometry": {"type": "Polygon", "coordinates": [_sq(cx - 0.00005, cy - 0.00002, 0.0001, 0.00004)]}}
    neighbour = {"type": "Feature", "properties": {"BLD_ID": "NEIGHBOUR", "AREA": 9000.0},
                 "geometry": {"type": "Polygon", "coordinates": [_sq(x0 - 0.0006, cy - 0.0003, 0.0006 + 0.00001, 0.0006)]}}
    fake_net.routes["LACounty_Parcel"] = _load("parcels_site1_60m.geojson")
    fake_net.routes["Countywide_Building_Outlines"] = json.dumps(
        {"type": "FeatureCollection", "features": [neighbour, inside]}).encode()
    fp = footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert fp.id == "INSIDE" and fp.provider == "lacounty_lariac_2020"
    assert x1 > x0  # parcel sanity


def _osm_way(i, lat, lng, dlat, dlng, tags=None):
    ring = [(lat, lng), (lat, lng + dlng), (lat + dlat, lng + dlng), (lat + dlat, lng), (lat, lng)]
    return {"type": "way", "id": i, "tags": {"building": "yes", **(tags or {})},
            "geometry": [{"lat": a, "lon": b} for a, b in ring]}


def test_osm_takes_largest_real_building_not_nearest_sliver(fake_net):
    lat, lng = 33.0, -118.0
    shed = _osm_way(1, lat + 0.00008, lng, 0.00003, 0.00003)  # ~10 m away, ~100 sq ft
    house = _osm_way(2, lat + 0.0001, lng + 0.0001, 0.00018, 0.00022)  # ~15 m away, ~2,000+ sq ft
    fake_net.routes["LACounty_Parcel"] = json.dumps({"features": []}).encode()
    fake_net.routes["overpass-api.de"] = json.dumps({"elements": [shed, house]}).encode()
    fp = footprint.fetch_footprint(lat, lng, ADDR)
    assert fp.provider == "osm" and fp.id == "2" and fp.area_sqft > 1000
    assert len(fp.other_buildings) == 1


def test_osm_prefers_matching_house_number_tag(fake_net):
    lat, lng = 33.0, -118.0
    a = _osm_way(1, lat + 0.0001, lng, 0.0002, 0.0002)
    b = _osm_way(2, lat + 0.0001, lng + 0.0004, 0.0001, 0.0001, {"addr:housenumber": "100"})
    fake_net.routes["LACounty_Parcel"] = json.dumps({"features": []}).encode()
    fake_net.routes["overpass-api.de"] = json.dumps({"elements": [a, b]}).encode()
    assert footprint.fetch_footprint(lat, lng, ADDR).id == "2"


def test_arcgis_error_is_not_cached_or_read_as_empty(fake_net, site1):
    """HTTP 200 with an error object: retried, never written to disk, and the county path reports failure."""
    fake_net.routes["LACounty_Parcel"] = json.dumps({"error": {"code": 500, "message": "boom"}}).encode()
    fake_net.routes["overpass"] = json.dumps({"elements": []}).encode()
    with pytest.raises(footprint.FootprintError):
        footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert not any(cache.cache_dir().glob("*.bin")) or all(
        b"boom" not in f.read_bytes() for f in cache.cache_dir().glob("*.bin"))
    # service recovers: the next call must succeed, not replay the cached error
    fake_net.routes["LACounty_Parcel"] = _load("parcels_site1_60m.geojson")
    fake_net.routes["Countywide_Building_Outlines"] = _load("buildings_parcel_site1.geojson")
    assert footprint.fetch_footprint(*_pt(site1), _addr(site1)).id == site1["footprint_id"]


def test_overpass_timeout_remark_is_not_cached(fake_net):
    fake_net.routes["LACounty_Parcel"] = json.dumps({"features": []}).encode()
    fake_net.routes["overpass-api.de"] = json.dumps({"elements": [], "remark": "runtime error: timed out"}).encode()
    fake_net.routes["overpass.kumi"] = json.dumps({"elements": [], "remark": "runtime error: timed out"}).encode()
    fake_net.routes["overpass.private"] = json.dumps({"elements": [], "remark": "timed out"}).encode()
    with pytest.raises(footprint.FootprintError):
        footprint.fetch_footprint(33.0, -118.0, ADDR)
    assert not any(b"remark" in f.read_bytes() for f in cache.cache_dir().glob("*.bin"))


def test_poisoned_cache_entry_is_refetched(fake_net):
    """An error body cached by an older version is discarded when the validator rejects it."""
    url = footprint.PARCEL_URL
    params = {"a": 1}
    path = cache.cache_dir() / (cache._key("GET", url, params, None) + ".bin")
    path.write_bytes(b'{"error": "old"}')
    fake_net.routes["LACounty_Parcel"] = b'{"features": []}'
    assert cache.fetch_json(url, params=params, check=footprint._arcgis_check) == {"features": []}


def test_cache_key_covers_params_expiry_and_temp_files(fake_net):
    fake_net.routes["example.test"] = b'{"ok": 1}'
    cache.fetch_bytes("https://example.test/a", params={"q": 1})
    cache.fetch_bytes("https://example.test/a", params={"q": 2})
    assert len(fake_net.calls) == 2  # different params, different entries
    cache.fetch_bytes("https://example.test/a", params={"q": 1})
    assert len(fake_net.calls) == 2  # fresh hit
    cache.fetch_bytes("https://example.test/a", params={"q": 1}, max_age_s=-1)
    assert len(fake_net.calls) == 3  # expired entries are refetched
    assert not list(cache.cache_dir().glob("*.tmp"))  # no stray temp files


def test_footprint_error_when_nothing_found(fake_net):
    fake_net.routes["LACounty_Parcel"] = json.dumps({"features": []}).encode()
    fake_net.routes["overpass"] = json.dumps({"elements": []}).encode()
    with pytest.raises(footprint.FootprintError, match="No building footprint"):
        footprint.fetch_footprint(40.0, -100.0, ADDR)


@network
def test_footprint_live(site1):
    fp = footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert fp.id == site1["footprint_id"]


def test_matched_parcel_without_building_raises_instead_of_osm(fake_net, site1):
    fake_net.routes["LACounty_Parcel"] = _load("parcels_site1_60m.geojson")
    fake_net.routes["Countywide_Building_Outlines"] = json.dumps({"type": "FeatureCollection", "features": []}).encode()
    fake_net.routes["overpass"] = _load("overpass_site1.json")  # must NOT be consulted
    with pytest.raises(footprint.FootprintError, match="parcel matched but has no building outline"):
        footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert not any("overpass" in u for u in fake_net.calls)


def test_county_layer_unreachable_falls_back_to_osm_with_warning(fake_net, site1, monkeypatch):
    import requests

    real = fake_net.routes
    real["overpass-api.de"] = _load("overpass_site1.json")

    def send(method, url, params, data, headers, timeout):
        fake_net.calls.append(url)
        if "LACounty_Parcel" in url:
            raise requests.ConnectionError("county down")
        return real["overpass-api.de"]

    monkeypatch.setattr(cache, "_send", send)
    fp = footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert fp.provider == "osm"
    assert fp.warnings[0] == "LA County layer unreachable; footprint from OpenStreetMap."


def test_county_outside_layer_is_silent_osm_fallback(fake_net, site1):
    fake_net.routes["LACounty_Parcel"] = json.dumps({"features": []}).encode()
    fake_net.routes["overpass-api.de"] = _load("overpass_site1.json")
    fp = footprint.fetch_footprint(*_pt(site1), _addr(site1))
    assert fp.provider == "osm" and not any("unreachable" in w for w in fp.warnings)


def test_building_layer_failure_after_parcel_match_raises(fake_net, site1, monkeypatch):
    import requests

    def send(method, url, params, data, headers, timeout):
        if "LACounty_Parcel" in url:
            return _load("parcels_site1_60m.geojson")
        raise requests.ConnectionError("buildings down")

    monkeypatch.setattr(cache, "_send", send)
    with pytest.raises(footprint.FootprintError, match="building layer could not be queried"):
        footprint.fetch_footprint(*_pt(site1), _addr(site1))
