"""The footprint chain with mocked HTTP: every link, the source it records, notes, deadline, ordering."""

import json
import time

import pytest
import requests

from roof_measure import cache, footprint, footprint_county, footprint_osm, footprint_solar
from roof_measure.deadline import Deadline, DeadlineExceeded
from roof_measure.footprint_types import AmbiguousBuilding, Footprint, FootprintError
from roof_measure.geocode import Address

LAT, LNG = 34.0, -118.0
ADDR = Address("100 Example Ave", "Sampletown", "CA", "90000")
D = 0.0001  # about 11 m


def ring(lat0, lng0, dlat, dlng):
    return [(lng0, lat0), (lng0 + dlng, lat0), (lng0 + dlng, lat0 + dlat), (lng0, lat0 + dlat), (lng0, lat0)]


def parcel(house="100"):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring(LAT - D, LNG - D, 5 * D, 5 * D)]},
            "properties": {"SitusHouseNo": house, "SitusStreet": "EXAMPLE AVE", "SitusDirection": "",
                           "SitusAddress": f"{house} EXAMPLE AVE", "AIN": "0000-000-000"}}


def building(i="B1", dlat=2 * D, dlng=2 * D):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring(LAT, LNG, dlat, dlng)]},
            "properties": {"BLD_ID": i, "HEIGHT": 15.0, "AREA": 2400.0}}


def osm_way(i, dlat=2 * D, dlng=2 * D, tags=None):
    pts = ring(LAT + D, LNG, dlat, dlng)
    return {"type": "way", "id": i, "tags": {"building": "yes", **(tags or {})},
            "geometry": [{"lat": y, "lon": x} for x, y in pts]}


class Net:
    """Routes cache.fetch_json by URL fragment; a value can be a dict, an exception, or a callable."""

    def __init__(self):
        self.routes, self.calls = {}, []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        for frag, val in self.routes.items():
            if frag in url:
                if callable(val):
                    return val(url, kw)
                if isinstance(val, Exception):
                    raise val
                return val
        raise AssertionError(f"unexpected request {url}")

    def urls(self):
        return [u for u, _ in self.calls]


@pytest.fixture
def net(monkeypatch):
    n = Net()
    monkeypatch.setattr(cache, "fetch_json", n)
    monkeypatch.delenv("GOOGLE_SOLAR_API_KEY", raising=False)
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: (_ for _ in ()).throw(FootprintError("no lidar")))
    return n


def county_ok(net, buildings=None, parcels=None):
    net.routes["LACounty_Parcel"] = {"features": parcels if parcels is not None else [parcel()]}
    net.routes["Countywide_Building_Outlines"] = {"features": buildings if buildings is not None else [building()]}


def test_county_link_wins_and_records_lariac(net):
    county_ok(net)
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "lariac" and fp.provider == "lacounty_lariac_2020" and fp.id == "B1" and fp.height_ft == 15.0
    assert not any("overpass" in u or "kumi" in u for u in net.urls())
    assert fp.warnings == [] and fp.warning_codes == []


def test_outside_the_county_goes_to_osm_all_mirrors_asked_at_once(net):
    net.routes["LACounty_Parcel"] = {"features": []}
    urls = footprint_osm.DEFAULT_OVERPASS_URLS
    net.routes[urls[0]] = requests.HTTPError("429 rate limited")
    net.routes[urls[1]] = {"elements": [osm_way(7)]}
    net.routes[urls[2]] = requests.HTTPError("502 at capacity")
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "osm" and fp.provider == "osm" and fp.id == "7"
    assert fp.warning_codes == ["footprint_osm"] and len(fp.warnings) == 1
    queries = [(u, kw) for u, kw in net.calls if "interpreter" in u]
    assert sorted(u for u, _ in queries) == sorted(urls)  # every mirror, none waited for another
    assert all("[timeout:25]" in kw["data"]["data"] and kw["timeout"] <= 45.0 and kw["retries"] == 0
               for _, kw in queries)


def test_a_slow_mirror_does_not_delay_a_fast_one(net):
    net.routes["LACounty_Parcel"] = {"features": []}
    urls = footprint_osm.DEFAULT_OVERPASS_URLS
    net.routes[urls[0]] = lambda url, kw: time.sleep(2.0) or {"elements": []}
    net.routes[urls[1]] = lambda url, kw: time.sleep(2.0) or {"elements": []}
    net.routes[urls[2]] = {"elements": [osm_way(8)]}
    start = time.monotonic()
    assert footprint.fetch_footprint(LAT, LNG, ADDR).id == "8"
    assert time.monotonic() - start < 1.0


def test_stage_cap_defaults_to_60_seconds_and_reads_the_env(monkeypatch):
    import importlib

    monkeypatch.delenv("ROOF_MEASURE_FOOTPRINT_S", raising=False)
    assert importlib.reload(footprint).FOOTPRINT_STAGE_S == 60.0
    monkeypatch.setenv("ROOF_MEASURE_FOOTPRINT_S", "42")
    assert importlib.reload(footprint).FOOTPRINT_STAGE_S == 42.0
    monkeypatch.delenv("ROOF_MEASURE_FOOTPRINT_S")
    importlib.reload(footprint)
    assert footprint_osm.MIRROR_TIMEOUT_S == 45.0


def test_overpass_calls_carry_the_cache_user_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path))
    seen = []
    monkeypatch.setattr(cache, "_send", lambda m, url, params, data, headers, timeout: seen.append(
        cache.USER_AGENT) or b'{"elements": []}')
    footprint_osm.fetch_overpass(LAT, LNG, urls=("https://x.test/api",))
    assert seen and seen[0] and "python-requests" not in seen[0]


def test_mirror_list_has_an_env_override():
    assert footprint_osm.mirror_urls({}) == footprint_osm.DEFAULT_OVERPASS_URLS
    assert footprint_osm.mirror_urls({"ROOF_MEASURE_OVERPASS_URLS": " https://a/x , https://b/y "}) == (
        "https://a/x", "https://b/y")
    assert all(u.split("/")[2].endswith("overpass-api.de") for u in footprint_osm.DEFAULT_OVERPASS_URLS)


def test_parcel_matched_without_a_building_falls_through_to_osm(net):
    county_ok(net, buildings=[])
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": [osm_way(9)]}
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "osm" and fp.id == "9"
    assert fp.warning_codes == ["parcel_without_building", "footprint_osm"] and len(fp.warnings) == 2


def test_county_layer_unreachable_falls_to_osm_with_a_note(net):
    net.routes["LACounty_Parcel"] = requests.ConnectionError("county down")
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": [osm_way(3)]}
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "osm" and fp.warnings[0] == "LA County layer unreachable; footprint from OpenStreetMap."
    assert fp.warning_codes == ["other", "footprint_osm"]


def test_building_layer_failure_after_a_parcel_match_falls_through_to_osm_with_a_note(net):
    net.routes["LACounty_Parcel"] = {"features": [parcel()]}
    net.routes["Countywide_Building_Outlines"] = requests.ConnectionError("down")
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": [osm_way(4)]}
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "osm" and fp.warning_codes == ["other", "footprint_osm"]
    assert "could not be queried" in fp.warnings[0] and "ConnectionError" in fp.warnings[0]


def test_outside_the_la_bbox_the_county_link_is_skipped(net):
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": [osm_way(6)]}
    fp = footprint.fetch_footprint(40.0, -105.0, ADDR)  # no LACounty route: asking it would fail the test
    assert fp.source == "osm" and not any("LACounty" in u for u in net.urls())


def test_weak_parcel_match_note_is_coded_other(net):
    county_ok(net, parcels=[parcel(house="102")])
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "lariac" and fp.warning_codes == ["other"] and "no exact parcel match" in fp.warnings[0]


def empty_osm(net):
    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": []}


def test_solar_link_needs_a_key_and_uses_segment_hull(net, monkeypatch):
    empty_osm(net)
    insights = {"name": "buildings/x", "solarPotential": {"roofSegmentStats": [
        {"boundingBox": {"sw": {"latitude": LAT, "longitude": LNG}, "ne": {"latitude": LAT + D, "longitude": LNG + D}}},
        {"boundingBox": {"sw": {"latitude": LAT + D, "longitude": LNG}, "ne": {"latitude": LAT + 2 * D, "longitude": LNG + 2 * D}}}]}}
    seen = []
    monkeypatch.setattr(footprint_solar.solar, "fetch_building_insights",
                        lambda lat, lng, key, timeout=30.0: seen.append(key) or insights)
    with pytest.raises(FootprintError, match="No building footprint"):  # no key: link skipped
        footprint.fetch_footprint(LAT, LNG, ADDR)
    assert seen == []
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "test-key")
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert seen == ["test-key"] and fp.source == "solar" and fp.provider == "solar"
    assert fp.warning_codes == ["footprint_solar"] and fp.polygon_wgs84.is_valid
    assert fp.polygon_wgs84.bounds == pytest.approx((LNG, LAT, LNG + 2 * D, LAT + 2 * D))
    assert "test-key" not in " ".join(fp.warnings)


def test_solar_unavailable_moves_on(net, monkeypatch):
    empty_osm(net)
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "k")

    def boom(*a, **k):
        raise footprint_solar.solar.SolarUnavailable("disabled")

    monkeypatch.setattr(footprint_solar.solar, "fetch_building_insights", boom)
    with pytest.raises(FootprintError, match="No building footprint"):
        footprint.fetch_footprint(LAT, LNG, ADDR)


def test_hull_link_is_last_and_records_lidar_hull(net, monkeypatch):
    empty_osm(net)
    from shapely.geometry import box

    hull = Footprint(provider="lidar_hull", id="lidar_hull", polygon_wgs84=box(LNG, LAT, LNG + D, LAT + D),
                     height_ft=20.0, area_sqft=1000.0, parcel_id=None, source="lidar_hull")
    hull.warn("footprint_lidar_hull", "from lidar")
    monkeypatch.setattr(footprint, "fetch_hull", lambda lat, lng, deadline=None: hull)
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "lidar_hull" and fp.warning_codes == ["footprint_lidar_hull"]


def test_ambiguous_building_from_the_hull_propagates(net, monkeypatch):
    empty_osm(net)

    def amb(*a, **k):
        raise AmbiguousBuilding("two")

    monkeypatch.setattr(footprint, "fetch_hull", amb)
    with pytest.raises(AmbiguousBuilding):
        footprint.fetch_footprint(LAT, LNG, ADDR)


def test_nothing_anywhere_is_no_footprint_and_all_mirrors_down_is_unreachable(net):
    empty_osm(net)
    with pytest.raises(FootprintError, match="No building footprint found"):
        footprint.fetch_footprint(LAT, LNG, ADDR)
    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = requests.ConnectionError("down")
    with pytest.raises(FootprintError, match="could not be reached"):
        footprint.fetch_footprint(LAT, LNG, ADDR)


def test_deadline_ends_the_osm_stage_even_when_every_mirror_hangs(net):
    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = lambda url, kw: time.sleep(3) or {"elements": []}
    start = time.monotonic()
    with pytest.raises((FootprintError, DeadlineExceeded)):
        footprint.fetch_footprint(LAT, LNG, ADDR, deadline=Deadline.after(0.4))
    assert time.monotonic() - start < 2.0


def test_an_expired_deadline_stops_before_the_lidar_link(net):
    empty_osm(net)
    with pytest.raises(DeadlineExceeded):
        footprint.fetch_footprint(LAT, LNG, ADDR, deadline=Deadline.after(0))


def test_overpass_remark_is_a_failure_not_an_empty_answer(net):
    net.routes["LACounty_Parcel"] = {"features": []}
    calls = []

    def run(url, kw):
        calls.append(url)
        footprint_osm._overpass_check({"remark": "runtime error: Query timed out"}) if len(calls) < 3 else None
        return {"elements": [osm_way(5)]}

    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = run
    assert footprint.fetch_footprint(LAT, LNG, ADDR).id == "5"


def test_osm_prefers_house_number_and_skips_slivers():
    payload = {"elements": [osm_way(1, D / 4, D / 4), osm_way(2, 2 * D, 2 * D), osm_way(3, D, D, {"addr:housenumber": "100"})]}
    fp = footprint_osm.parse_osm(payload, LAT, LNG, ADDR)
    assert fp.id == "3" and fp.match == "exact" and fp.source == "osm" and len(fp.other_buildings) == 2
    payload["elements"].pop()
    assert footprint_osm.parse_osm(payload, LAT, LNG, ADDR).id == "2"
    assert footprint_osm.parse_osm({"elements": []}, LAT, LNG, ADDR) is None


def test_old_import_names_still_work():
    assert footprint.PARCEL_URL == footprint_county.PARCEL_URL and callable(footprint.pick_parcel)
    assert footprint._area_sqft(osm_way(1) and footprint_osm.parse_osm({"elements": [osm_way(1)]}, LAT, LNG).polygon_wgs84) > 1000
    assert json.dumps(footprint.OVERPASS_URLS)


def test_osm_outage_is_a_skipped_link_the_hull_still_runs(net, monkeypatch):
    from shapely.geometry import box

    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = requests.ConnectionError("down")
    hull = Footprint(provider="lidar_hull", id="lidar_hull", polygon_wgs84=box(LNG, LAT, LNG + D, LAT + D),
                     height_ft=20.0, area_sqft=1000.0, parcel_id=None, source="lidar_hull")
    hull.warn("footprint_lidar_hull", "from lidar")
    monkeypatch.setattr(footprint, "fetch_hull", lambda lat, lng, deadline=None: hull)
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "lidar_hull"
    assert fp.warning_codes == ["other", "footprint_lidar_hull"] and "OpenStreetMap could not be reached" in fp.warnings[0]


def test_a_used_up_stage_cap_does_not_stop_the_chain(net, monkeypatch):
    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": []}
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "k")
    monkeypatch.setattr(footprint, "FOOTPRINT_STAGE_S", 0.0)
    called = []
    monkeypatch.setattr(footprint, "fetch_solar", lambda *a, **k: called.append("solar"))

    def hull(lat, lng, deadline=None):
        called.append("hull")
        raise FootprintError("no smooth roof")

    monkeypatch.setattr(footprint, "fetch_hull", hull)
    with pytest.raises(FootprintError, match="No building footprint"):
        footprint.fetch_footprint(LAT, LNG, ADDR, deadline=Deadline.after(100))
    assert called == ["hull"]  # solar skipped (stage spent), hull still attempted


def test_every_link_failed_with_one_unreachable_is_upstream_unavailable_with_the_hull_reason(net, monkeypatch):
    from roof_measure.errors import code_for

    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = requests.ConnectionError("down")
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: (_ for _ in ()).throw(FootprintError("no smooth roof")))
    with pytest.raises(FootprintError) as e:
        footprint.fetch_footprint(LAT, LNG, ADDR)
    assert code_for(e.value) == "upstream_unavailable" and "no smooth roof" in str(e.value)
