"""Data layer tests: LiDAR project selection and point cloud IO (offline)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import numpy as np
import pytest

from roof_measure import cache, lidar

_skip = pytest.mark.skipif(not os.environ.get("ROOF_MEASURE_NETWORK"), reason="needs network")


def network(fn):
    """Mark a test as needing the live network; skipped unless ROOF_MEASURE_NETWORK=1."""
    return pytest.mark.network(_skip(fn))


# ---------------------------------------------------------------- lidar
def test_project_year_parsing():
    assert lidar.project_year("CA_LosAngeles_1_B23") == 2023
    assert lidar.project_year("USGS_LPC_CA_LosAngeles_2016_LAS_2018") == 2016
    assert lidar.project_year("CA_OrangeCo_2011") == 2011
    assert lidar.project_year("Foo") is None


def test_gps_to_date_and_range():
    # adjusted GPS time 0 is 2011-09-14 (GPS epoch + 1e9 s)
    assert lidar.gps_to_date(0.0) == "2011-09-14"
    t0 = (datetime(2023, 10, 15, tzinfo=UTC) - lidar.GPS_EPOCH).total_seconds() - lidar.ADJUSTED_GPS_OFFSET_S
    rng = lidar.acquired_range(np.array([t0, t0 + 86400 * 5]))
    a, b = rng.split("/")
    assert a < b and a.startswith("2023")
    assert lidar.acquired_range(np.zeros(3)) is None


def test_point_cloud_npz_round_trip(tmp_path):
    pc = lidar.PointCloud(np.arange(5.0), np.arange(5.0) * 2, np.ones(5), np.array([2, 1, 1, 2, 1], np.uint8),
                          np.arange(5.0), {"epsg": 32611, "project": "p"})
    f = tmp_path / "a.npz"
    lidar.save_npz(pc, f)
    back = lidar.load_npz(f)
    assert np.array_equal(back.x, pc.x) and back.meta == pc.meta and len(back) == 5


def test_select_project_ranks_by_density_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path / "c"))

    def sq(x0, y0, x1, y1):
        return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}

    feats = [
        {"geometry": sq(-119, 33, -118, 34), "properties": {"name": "CA_LosAngeles_1_B23", "count": 10**9,
                                                            "url": "https://x/CA_LosAngeles_1_B23/ept.json"}},
        {"geometry": sq(-119, 33, -118, 34), "properties": {"name": "USGS_LPC_CA_LosAngeles_2016_LAS_2018",
                                                            "count": 10**10, "url": "https://x/old/ept.json"}},
        {"geometry": sq(-119, 33, -118, 34), "properties": {"name": "CA_OtherPlace_2020", "count": 10**9,
                                                            "url": "https://x/B/ept.json"}},
        {"geometry": sq(10, 10, 11, 11), "properties": {"name": "Elsewhere_2024", "count": 1, "url": "https://x/e"}},
    ]
    ept = json.dumps({"srs": {"horizontal": "3857"}, "bounds": [0] * 6, "schema": []}).encode()

    def send(method, url, params, data, headers, timeout):
        if url == lidar.RESOURCES_URL:
            return json.dumps({"features": feats}).encode()
        if url.endswith("ept.json"):
            return ept
        raise AssertionError(url)

    monkeypatch.setattr(cache, "_send", send)
    ranked = lidar.select_project(33.5, -118.5)
    names = [p.name for p in ranked]
    # the 2016 survey (~1/m2) is the densest of three thin ones; equal densities: newest first.
    assert names[0] == "USGS_LPC_CA_LosAngeles_2016_LAS_2018"
    assert names[1:] == ["CA_LosAngeles_1_B23", "CA_OtherPlace_2020"]
    assert "Elsewhere_2024" not in names
    assert ranked[0].year == 2016 and ranked[1].year == 2023 and ranked[0].span_m > 50_000


@network
def test_lidar_live_points_small_box(site1):
    projects = lidar.select_project(site1["origin"]["lat"], site1["origin"]["lng"])
    assert projects[0].year >= 2016
    pc = lidar.fetch_points(projects[0], site1["lidar_box_center"]["lat"], site1["lidar_box_center"]["lon"], 20, 32611)
    assert len(pc) > 5000
