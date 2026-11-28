"""Review round 3, what outlives the job service: outage fall-throughs are flagged transient, and a LiDAR tile's HTTP
status decides permanent or outage."""

from types import SimpleNamespace as NS

import pytest
import requests
from test_footprint_chain import ADDR, LAT, LNG, D, building, osm_way, parcel

from roof_measure import footprint, footprint_osm, lidar
from roof_measure.errors import code_for
from roof_measure.footprint_types import FootprintError, FootprintUnavailable


# ---- NW1 / S1: an outage fall-through is flagged transient and never cached
def osm_ok(net):
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": [osm_way(7)]}


def test_county_down_then_osm_is_transient_and_a_clean_run_is_not(net):
    net.routes["LACounty_Parcel"] = requests.ConnectionError("down")
    osm_ok(net)
    fp = footprint.fetch_footprint(LAT, LNG, ADDR)
    assert fp.source == "osm" and fp.transient is True
    net.routes["LACounty_Parcel"] = {"features": []}  # outside the county layer: a miss, not an outage
    assert footprint.fetch_footprint(LAT, LNG, ADDR).transient is False
    net.routes["LACounty_Parcel"] = {"features": [parcel()]}
    net.routes["Countywide_Building_Outlines"] = {"features": [building()]}
    assert footprint.fetch_footprint(LAT, LNG, ADDR).transient is False


def test_osm_down_then_hull_is_transient(net, monkeypatch):
    from shapely.geometry import box

    from roof_measure.footprint_types import Footprint

    net.routes["LACounty_Parcel"] = {"features": []}
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = requests.ConnectionError("down")
    hull = Footprint(provider="lidar_hull", id="h", polygon_wgs84=box(LNG, LAT, LNG + D, LAT + D), height_ft=1.0,
                     area_sqft=1.0, parcel_id=None, source="lidar_hull")
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: hull)
    assert footprint.fetch_footprint(LAT, LNG, ADDR).transient is True


def test_every_link_down_including_the_county_is_upstream_unavailable(net, monkeypatch):
    net.routes["LACounty_Parcel"] = requests.ConnectionError("down")
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = {"elements": []}
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: (_ for _ in ()).throw(FootprintError("none")))
    with pytest.raises(FootprintUnavailable) as e:
        footprint.fetch_footprint(LAT, LNG, ADDR)
    assert code_for(e.value) == "upstream_unavailable" and "LA County" in str(e.value)


# ---- lidar: 4xx is permanent, 5xx and 429 are outages
@pytest.mark.parametrize("status,outage", [(404, False), (403, False), (500, True), (503, True), (429, True)])
def test_a_tile_http_status_decides_permanent_or_outage(monkeypatch, status, outage):
    err = requests.HTTPError(f"{status}")
    err.response = NS(status_code=status)
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: [lidar.LidarProject("p", "u", 2020, 1.0, 1.0)])
    monkeypatch.setattr(lidar, "fetch_points", lambda *a: (_ for _ in ()).throw(err))
    with pytest.raises(lidar.LidarError) as e:
        lidar.fetch_best_points(34.0, -118.0, 30, 32611, footprint_m=None)
    assert isinstance(e.value, lidar.LidarUnavailable) is outage
