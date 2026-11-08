"""Data layer tests: LiDAR project selection / point cloud IO and block segmentation (offline)."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime

import numpy as np
import pytest
from shapely.geometry import Polygon, shape
from sites import local_data_path

from roof_measure import cache, lidar
from roof_measure.blocks import SCHEMA, segment_blocks
from roof_measure.frame import FT_PER_M, Frame

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


def test_select_project_ranks_newest_then_densest(tmp_path, monkeypatch):
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
    # newest year first; within one year, densest first. The 2016 survey is last despite the highest count.
    assert names[0] == "CA_LosAngeles_1_B23" and names[1] == "CA_OtherPlace_2020"
    assert names[-1] == "USGS_LPC_CA_LosAngeles_2016_LAS_2018"
    assert "Elsewhere_2024" not in names
    assert ranked[0].year == 2023 and ranked[-1].year == 2016 and ranked[0].span_m > 50_000


@network
def test_lidar_live_points_small_box(site1):
    projects = lidar.select_project(site1["origin"]["lat"], site1["origin"]["lng"])
    assert projects[0].year >= 2016
    pc = lidar.fetch_points(projects[0], site1["lidar_box_center"]["lat"], site1["lidar_box_center"]["lon"], 20, 32611)
    assert len(pc) > 5000


# ---------------------------------------------------------------- blocks
def _local(name):
    path = local_data_path(name)
    if path is None:
        pytest.skip(f"local/test-data/{name} missing")
    return path


@pytest.fixture(scope="module")
def site1_blocks(site1):
    fp = shape(json.loads(_local("buildings_parcel_site1.geojson").read_text())["features"][0]["geometry"])
    frame, fp_m = Frame.for_footprint(fp)
    pc = lidar.PointCloud.from_npz(_local("site1_roof.pts"))
    bs = segment_blocks(pc, fp_m, frame, address={"line1": site1["line1"]},
                        footprint_meta={"provider": "lacounty_lariac_2020", "id": site1["footprint_id"]})
    return bs


def test_hip_faces_are_separate_sloped_blocks(site1_blocks):
    west = [b for b in site1_blocks.blocks if b.kind == "sloped"
            and b.polygon_m.centroid.x * FT_PER_M < 50 and 3.5 <= b.pitch_rise <= 4.3]
    assert len(west) >= 4  # the hip block spans x 13-48 ft, so "west" means centroid x < 50 ft
    true_area = sum(b.plan_area_sqft * math.sqrt(1 + (b.pitch_rise / 12) ** 2) for b in west)
    assert 800 <= true_area <= 1100  # the roof overhangs the outline by up to 1 m
    assert len({round(b.aspect_deg / 45) % 8 for b in west}) >= 4  # four different facing directions


def test_flat_blocks_cover_most_of_the_roof(site1_blocks):
    flats = [b for b in site1_blocks.blocks if b.kind == "flat"]
    assert sum(b.plan_area_sqft for b in flats) > 3000
    assert all(b.pitch_rise <= 0.5 and b.aspect_deg is None for b in flats)


def test_small_sloped_block_touches_south_outline(site1_blocks):
    """The south-facing awning at x 55-65 ft survives the 0.6 m overhang clip (the x 112-123 ft one,
    which sits mostly outside the county outline, does not: see the data-layer report)."""
    fp = site1_blocks.footprint_m
    found = []
    for b in site1_blocks.blocks:
        x_ft = b.polygon_m.centroid.x * FT_PER_M
        if (b.kind == "sloped" and 1.5 <= b.polygon_m.area <= 40 and 50 <= x_ft <= 130
                and 150 < (b.aspect_deg or 0) < 210 and b.polygon_m.distance(fp.exterior) < 0.6):
            found.append(b.id)
    assert len(found) >= 1


def test_json_schema_shape(site1_blocks, tmp_path):
    out = tmp_path / "b.json"
    site1_blocks.to_json(out)
    d = json.loads(out.read_text())
    assert d["schema"] == SCHEMA == "bond.roof_blocks/0.1"
    assert set(d) == {"schema", "address", "origin", "frame", "footprint_ft", "footprint_meta", "lidar",
                      "blocks", "borders", "outline_edges", "extra"}
    ring = d["footprint_ft"]
    assert ring[0] == ring[-1] and min(p[0] for p in ring) == pytest.approx(0, abs=0.05)
    assert min(p[1] for p in ring) == pytest.approx(0, abs=0.05)
    assert Polygon(ring).exterior.is_ccw
    assert d["frame"]["epsg"] == 32611
    for k in ("project", "acquired", "year", "points_on_roof", "density_per_m2", "ground_z_m", "epsg"):
        assert k in d["lidar"]
    assert d["lidar"]["points_on_roof"] > 8000
    assert d["lidar"]["acquired"].startswith("2023-")
    ids = {b["id"] for b in d["blocks"]}
    for b in d["blocks"]:
        assert set(b) == {"id", "kind", "polygon_ft", "plan_area_sqft", "plan_area_in_footprint_sqft", "mean_z_ft", "height_above_ground_ft",
                          "pitch_rise", "aspect_deg", "rms_ft", "n_cells"}
        poly = Polygon(b["polygon_ft"])
        assert poly.is_valid and b["polygon_ft"][0] == b["polygon_ft"][-1]
        assert poly.area == pytest.approx(b["plan_area_sqft"], rel=0.02)
        assert b["kind"] in ("flat", "sloped") and (b["kind"] == "flat") == (b["aspect_deg"] is None)
    for e in d["borders"]:
        assert e["a"] in ids and e["b"] in ids and e["length_ft"] > 0 and e["step_ft"] >= 0
    assert {e["block"] for e in d["outline_edges"]} == ids
    # hip faces share borders of 10-19 ft with each other
    hips = {b["id"] for b in d["blocks"] if b["kind"] == "sloped" and 3.5 <= b["pitch_rise"] <= 4.3}
    hip_borders = [e for e in d["borders"] if e["a"] in hips and e["b"] in hips]
    assert hip_borders and all(5 <= e["length_ft"] <= 30 for e in hip_borders)


def test_debug_png_written(site1_blocks, tmp_path):
    p = tmp_path / "blocks_debug.png"
    site1_blocks.save_debug_png(p)
    assert p.read_bytes()[:4] == b"\x89PNG" and p.stat().st_size > 20_000


def test_too_few_points_raises():
    fp = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    frame = Frame(epsg=32611, x0_m=0, y0_m=0, origin_lat=0.0, origin_lng=0.0)
    pc = lidar.PointCloud(np.array([1.0]), np.array([1.0]), np.array([5.0]), np.array([1], np.uint8),
                          np.zeros(1), {})
    with pytest.raises(ValueError, match="Too few"):
        segment_blocks(pc, fp, frame)
