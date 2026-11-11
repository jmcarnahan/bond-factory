"""Generalisation tests from the adversarial review: steep and sparse roofs, merging, LiDAR choice, box size."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Polygon, box, shape

from roof_measure import blocks, cache, lidar
from roof_measure.blocks import BlocksError, segment_blocks
from roof_measure.frame import Frame
from roof_measure.lidar import LidarTooSparse, PointCloud

X0, Y0 = 377000.0, 3742000.0


def gable(pitch: float, density: float, w: float = 10.0, length: float = 15.0, seed: int = 1) -> PointCloud:
    """Perfect E-W gable (ridge along x), eave 3 m above ground, 2 cm noise, ground around it."""
    rng = np.random.default_rng(seed)
    n = int(density * (length + 4) * (w + 4))
    x = rng.uniform(-2, length + 2, n)
    y = rng.uniform(-2, w + 2, n)
    roof = (x >= 0) & (x <= length) & (y >= 0) & (y <= w)
    z = np.zeros(n)
    cl = np.full(n, 2, np.uint8)
    z[roof] = 3 + (w / 2 - np.abs(y - w / 2))[roof] * pitch / 12 + rng.normal(0, 0.02, roof.sum())
    cl[roof] = 1
    z[~roof] += rng.normal(0, 0.02, (~roof).sum())
    return PointCloud(x + X0, y + Y0, z, cl, np.zeros(n), {"epsg": 32611, "project": "synthetic", "year": 2024})


def run_gable(pitch: float, density: float = 20.0):
    fp = box(X0, Y0, X0 + 15, Y0 + 10)
    return segment_blocks(gable(pitch, density), fp, Frame.from_footprint_m(fp, 32611)), fp


def opposite(a: float, b: float) -> bool:
    return abs((a - b + 180) % 360 - 180) > 160


@pytest.mark.parametrize("pitch", [4, 9, 12])
def test_synthetic_gable_gives_two_opposite_faces_at_any_pitch(pitch):
    bs, fp = run_gable(pitch)
    sloped = [b for b in bs.blocks if b.kind == "sloped"]
    assert len(bs.blocks) == 2 and len(sloped) == 2
    assert opposite(sloped[0].aspect_deg, sloped[1].aspect_deg)
    assert all(abs(b.pitch_rise - pitch) < 0.3 for b in sloped)
    cover = sum(b.plan_area_sqft for b in bs.blocks) / (fp.area * 10.7639)
    assert 0.9 <= cover <= 1.12


def test_synthetic_gable_plan_area_within_5_percent_of_truth():
    bs, fp = run_gable(5)
    true_sqft = fp.area * 10.7639
    total = sum(b.plan_area_sqft for b in bs.blocks)
    assert true_sqft <= total <= 1.05 * true_sqft
    assert sum(b.plan_area_in_footprint_sqft for b in bs.blocks) == pytest.approx(true_sqft, rel=0.03)
    assert all(b.plan_area_in_footprint_sqft <= b.plan_area_sqft + 1e-6 for b in bs.blocks)


def test_eight_square_metre_shed_is_86_to_110_sqft():
    fp = box(X0, Y0, X0 + 4.0, Y0 + 2.0)  # 8 m2 = 86 sq ft, pitch 4/12 shed-sized gable
    bs = segment_blocks(gable(4, 60, w=2.0, length=4.0), fp, Frame.from_footprint_m(fp, 32611))
    assert 86 * 0.97 <= sum(b.plan_area_sqft for b in bs.blocks) <= 110


def test_sparse_cloud_raises_with_project_year_and_density():
    fp = box(X0, Y0, X0 + 15, Y0 + 10)
    with pytest.raises(LidarTooSparse, match=r"synthetic \(2024\).*points/m2") as e:
        segment_blocks(gable(5, 2.0), fp, Frame.from_footprint_m(fp, 32611))
    assert e.value.density < 4


def test_blocks_error_when_too_few_points_or_nothing_survives():
    fp = box(X0, Y0, X0 + 15, Y0 + 10)
    frame = Frame.from_footprint_m(fp, 32611)
    tiny = PointCloud(np.array([X0 + 1]), np.array([Y0 + 1]), np.array([5.0]), np.array([1], np.uint8),
                      np.zeros(1), {})
    with pytest.raises(BlocksError):
        segment_blocks(tiny, fp, frame)
    # dense noise: every cell non-planar, so no block survives; must raise, not return an empty set
    rng = np.random.default_rng(0)
    n = 20000
    x, y = rng.uniform(0, 15, n), rng.uniform(0, 10, n)
    noise = PointCloud(x + X0, y + Y0, 3 + rng.uniform(-1.0, 1.0, n), np.ones(n, np.uint8), np.zeros(n), {})
    with pytest.raises(BlocksError, match="No roof block"):
        segment_blocks(noise, fp, frame)


def _grid(n=20, cell=0.25):
    xs = (np.arange(n) + 0.5) * cell
    return np.meshgrid(xs, xs)


def test_merge_coplanar_joins_one_plane_and_keeps_a_step():
    gx, gy = _grid()
    val = 0.3 * gx + 3.0  # one sloped plane (aspect 270, pitch ~3.6/12)
    lab = np.where(gx < 2.5, 0, 1)
    flab = lab.copy()
    blocks._merge_coplanar(lab, flab, val, gx, gy, 0.25)
    assert len(np.unique(lab)) == 1 and len(np.unique(flab)) == 1
    stepped = val + np.where(gx >= 2.5, 0.4, 0.0)  # same slope, 0.4 m higher on the right: a real step
    lab = np.where(gx < 2.5, 0, 1)
    flab = lab.copy()
    blocks._merge_coplanar(lab, flab, stepped, gx, gy, 0.25)
    assert len(np.unique(lab)) == 2
    other = np.where(gx < 2.5, 0.3 * gx, -0.3 * gx + 1.5) + 3.0  # opposite aspects meeting at a ridge
    lab = np.where(gx < 2.5, 0, 1)
    flab = lab.copy()
    blocks._merge_coplanar(lab, flab, other, gx, gy, 0.25)
    assert len(np.unique(lab)) == 2


def _house(tag: str, local_data):
    fp = shape(json.loads(local_data(f"{tag}_footprint.geojson").read_text())["geometry"])
    frame, fp_m = Frame.for_footprint(fp)
    pc = PointCloud.from_npz(local_data(f"{tag}_roof.pts"))
    return segment_blocks(pc, fp_m, frame), fp_m


def test_site3_gable_is_two_aspect_families_and_covers_the_footprint(local_data):
    bs, fp_m = _house("site3", local_data)
    cover = sum(b.plan_area_sqft for b in bs.blocks) / (fp_m.area * 10.7639)
    assert 0.97 <= cover <= 1.12
    assert all(b.kind == "sloped" and 2.8 <= b.pitch_rise <= 3.6 for b in bs.blocks)
    families = {round(b.aspect_deg / 90) % 4 for b in bs.blocks}
    assert families == {1, 3}  # east and west


def test_site2_hip_has_four_faces_and_covers_the_footprint(local_data):
    bs, fp_m = _house("site2", local_data)
    cover = sum(b.plan_area_sqft for b in bs.blocks) / (fp_m.area * 10.7639)
    assert 0.97 <= cover <= 1.12
    faces = [b for b in bs.blocks if b.kind == "sloped" and b.plan_area_sqft > 150 and 3.0 <= b.pitch_rise <= 4.5]
    assert {round(b.aspect_deg / 90) % 4 for b in faces} == {0, 1, 2, 3}
    assert len(bs.blocks) <= 6


# ---------------------------------------------------------------- lidar choice and box size
def _cloud(n_inside: int, fp: Polygon, project: str = "p") -> PointCloud:
    rng = np.random.default_rng(0)
    minx, miny, maxx, maxy = fp.bounds
    x = rng.uniform(minx, maxx, n_inside)
    y = rng.uniform(miny, maxy, n_inside)
    return PointCloud(np.r_[x, minx - 5], np.r_[y, miny - 5], np.r_[np.full(n_inside, 5.0), 0.0],
                      np.r_[np.ones(n_inside), 2].astype(np.uint8), np.zeros(n_inside + 1),
                      {"project": project, "year": 2023})


def _projects():
    return [lidar.LidarProject("new_2023", "u/new", 2023, 1.0, 1000.0),
            lidar.LidarProject("old_2016", "u/old", 2016, 1.0, 1000.0)]


def test_thin_newest_project_falls_back_to_older_and_says_so(monkeypatch):
    fp = box(0, 0, 10, 10)
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: _projects())
    monkeypatch.setattr(lidar, "fetch_points",
                        lambda p, *a: _cloud(100 if p.name.startswith("new") else 1500, fp, p.name))
    pc = lidar.fetch_best_points(33.0, -118.0, 30, 32611, footprint_m=fp)
    assert pc.meta["project"] == "old_2016" and pc.meta["fallback_used"] is True
    assert "new_2023" in pc.meta["skipped"][0]
    monkeypatch.setattr(lidar, "fetch_points", lambda p, *a: _cloud(1500, fp, p.name))
    assert lidar.fetch_best_points(33.0, -118.0, 30, 32611, footprint_m=fp).meta["fallback_used"] is False


def test_every_project_thin_raises_too_sparse_naming_the_best(monkeypatch):
    fp = box(0, 0, 10, 10)
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: _projects())
    monkeypatch.setattr(lidar, "fetch_points",
                        lambda p, *a: _cloud(100 if p.name.startswith("new") else 300, fp, p.name))
    with pytest.raises(LidarTooSparse, match=r"old_2016 \(2016\) gives 3\.0 points/m2"):
        lidar.fetch_best_points(33.0, -118.0, 30, 32611, footprint_m=fp)


def test_min_points_counts_footprint_not_box(monkeypatch):
    """Lots of points in the box but few on the roof must not pass."""
    fp = box(0, 0, 10, 10)
    pc = _cloud(50, fp)
    ground = PointCloud(np.linspace(-40, -20, 5000), np.linspace(-40, -20, 5000), np.zeros(5000),
                        np.full(5000, 2, np.uint8), np.zeros(5000), {})
    merged = PointCloud(np.r_[pc.x, ground.x], np.r_[pc.y, ground.y], np.r_[pc.z, ground.z],
                        np.r_[pc.classification, ground.classification], np.zeros(5051), pc.meta)
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: _projects()[:1])
    monkeypatch.setattr(lidar, "fetch_points", lambda p, *a: merged)
    with pytest.raises(LidarTooSparse):
        lidar.fetch_best_points(33.0, -118.0, 30, 32611, footprint_m=fp)


def test_box_is_footprint_bbox_plus_15m_each_side(monkeypatch):
    seen = {}
    monkeypatch.setattr(lidar, "fetch_best_points",
                        lambda lat, lng, half, epsg, **kw: seen.update(half=half, lat=lat, lng=lng) or None)
    fp = box(372000, 3745000, 372105, 3745043)  # 344 x 141 ft building
    lidar.fetch_for_footprint(fp, 32611)
    assert seen["half"] == pytest.approx(52.5 + 15)  # box side = 105 m + 30 m = 135 m
    assert 33.8 < seen["lat"] < 33.9


def test_fetch_points_records_box_and_fallback_meta_keys():
    meta_keys = {"box_m", "half_size_m", "project", "year", "acquired"}
    src = (Path(lidar.__file__)).read_text()
    assert all(f'"{k}"' in src for k in meta_keys)


# ---------------------------------------------------------------- project year
@pytest.mark.parametrize("name,year", [
    ("CA_LosAngeles_1_B23", 2023), ("USGS_LPC_CA_LosAngeles_2016_LAS_2018", 2016),
    ("CA_FEMALevee_1_D23", 2023), ("CA_FEMAR9Southeast_1_D24", 2024), ("CA_SolanoCounty_1_A23", 2023),
    ("AK_NorthSlope_B11_2018", 2018), ("USGS_LPC_IN_WT_B11_Putnam_2013_LAS_2016", 2013),
    ("LA_BretonIsl_Topobathymetric_D22", 2022), ("ND_SouthWest_1_D21", 2021), ("VT_Statewide_2_A23", 2023),
    ("IA_FullState", None),
])
def test_project_year_reviewer_names(name, year):
    assert lidar.project_year(name) == year


def test_project_year_block_number_is_never_a_year():
    assert lidar.project_year("KS_Statewide_B13_2018") == 2018
    assert lidar.project_year("XX_Place_B10_Sub") is None  # B10 is mid-name, not a trailing year token


def test_resources_garbage_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path))
    monkeypatch.setattr(cache.time, "sleep", lambda _s: None)
    body = {"v": b"<html>rate limited</html>"}
    monkeypatch.setattr(cache, "_send", lambda *a, **k: body["v"])
    with pytest.raises(cache.BadResponse):
        lidar._load_resources()
    assert not list(Path(tmp_path).glob("*.bin"))
    body["v"] = json.dumps({"features": [{"properties": {"name": "x"}, "geometry": None}]}).encode()
    assert len(lidar._load_resources()) == 1



# ---------------------------------------------------------------- vertical units, corrupt nodes, county failures
def _ept(wkt: str = "", vertical: str | None = None) -> dict:
    srs = {"horizontal": "3857", "wkt": wkt}
    if vertical:
        srs["vertical"] = vertical
    return {"bounds": [-13_200_000, 4_000_000, -100, -13_100_000, 4_100_000, 100], "srs": srs, "schema": []}


def test_vertical_scale_reads_feet_metres_and_unknown():
    foot = 'COMPD_CS["x",PROJCS["p"],VERT_CS["NAVD88 height (ftUS)",VERT_DATUM["N",2005],UNIT["US survey foot",0.3048006096012192]]]'
    assert lidar.vertical_scale(_ept(foot)) == (pytest.approx(0.3048006), None)
    assert lidar.vertical_scale(_ept(vertical="6360"))[0] == pytest.approx(0.3048006)
    assert lidar.vertical_scale(_ept(vertical="5703")) == (1.0, None)
    scale, warning = lidar.vertical_scale(_ept("PROJCS[...]"))
    assert scale == 1.0 and "vertical unit" in warning and "metres" in warning


def _fake_epsg3857_node(z_ft: float):
    """A one-node EPT around an arbitrary point with every point at z_ft feet, plus the routes that serve it."""
    import io

    import laspy
    from pyproj import Transformer

    cx, cy = Transformer.from_crs(4326, 3857, always_xy=True).transform(-118.5, 33.5)
    hdr = laspy.LasHeader(point_format=6, version="1.4")
    hdr.offsets = [cx, cy, 0.0]
    hdr.scales = [0.01, 0.01, 0.01]
    las = laspy.LasData(hdr)
    las.x = cx + np.linspace(-5, 5, 50)
    las.y = cy + np.linspace(-5, 5, 50)
    las.z = np.full(50, z_ft)
    las.classification = np.full(50, 2, np.uint8)
    buf = io.BytesIO()
    las.write(buf, do_compress=True)
    ept = {"bounds": [cx - 500, cy - 500, -1000, cx + 500, cy + 500, 1000], "srs": {"horizontal": "3857"},
           "schema": []}
    return buf.getvalue(), ept


def _route_ept(monkeypatch, laz: bytes, hierarchy: bytes = b'{"0-0-0-0": 50}'):
    def send(method, url, params, data, headers, timeout):
        if "ept-hierarchy" in url:
            return hierarchy
        if "ept-data" in url:
            return laz
        raise AssertionError(url)

    monkeypatch.setattr(cache, "_send", send)
    monkeypatch.setattr(cache.time, "sleep", lambda _s: None)


def _proj(ept: dict) -> lidar.LidarProject:
    return lidar.LidarProject("fake_2023", "https://x/fake/ept.json", 2023, 1.0, 1000.0, ept=ept)


def test_fetch_points_scales_feet_to_metres_and_warns_when_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path))
    laz, ept = _fake_epsg3857_node(100.0)
    _route_ept(monkeypatch, laz)
    unknown = lidar.fetch_points(_proj(ept), 33.5, -118.5, 20, 32611)
    assert np.allclose(unknown.z, 100.0, atol=0.02) and any("vertical unit" in w for w in unknown.meta["warnings"])
    ept_ft = {**ept, "srs": {"horizontal": "3857", "vertical": "8228"}}
    feet = lidar.fetch_points(_proj(ept_ft), 33.5, -118.5, 20, 32611)
    assert np.allclose(feet.z, 30.48, atol=0.02) and feet.meta["warnings"] == [] and feet.meta["z_scale"] == 0.3048


def test_corrupt_cached_laz_is_deleted_and_raises_lidar_error(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path))
    _, ept = _fake_epsg3857_node(10.0)
    _route_ept(monkeypatch, b"this is not a laz file" * 20)
    with pytest.raises(lidar.LidarError, match="corrupt LiDAR node"):
        lidar.fetch_points(_proj(ept), 33.5, -118.5, 20, 32611)
    assert not any(b"not a laz" in f.read_bytes() for f in Path(tmp_path).glob("*.bin"))  # evicted
    good, _ = _fake_epsg3857_node(10.0)
    _route_ept(monkeypatch, good)  # a retry downloads a fresh copy
    assert len(lidar.fetch_points(_proj(ept), 33.5, -118.5, 20, 32611)) == 50


def test_garbage_hierarchy_is_rejected_and_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path))
    laz, ept = _fake_epsg3857_node(10.0)
    _route_ept(monkeypatch, laz, hierarchy=b"{}")
    with pytest.raises(cache.BadResponse):
        lidar.fetch_points(_proj(ept), 33.5, -118.5, 20, 32611)
    assert not list(Path(tmp_path).glob("*.bin"))


def test_project_listing_failure_becomes_lidar_error(monkeypatch):
    import requests

    def boom(lat, lng):
        raise requests.ConnectionError("github unreachable")

    monkeypatch.setattr(lidar, "select_project", boom)
    with pytest.raises(lidar.LidarError, match="Could not list USGS 3DEP projects"):
        lidar.fetch_best_points(33.8, -118.3, 30, 32611)


def test_corrupt_project_falls_through_to_next(monkeypatch):
    fp = box(0, 0, 10, 10)
    monkeypatch.setattr(lidar, "select_project", lambda lat, lng: _projects())

    def fetch(p, *a):
        if p.name.startswith("new"):
            raise lidar.LidarError("new_2023: corrupt LiDAR node 3-1-1-1")
        return _cloud(1500, fp, p.name)

    monkeypatch.setattr(lidar, "fetch_points", fetch)
    pc = lidar.fetch_best_points(33.0, -118.0, 30, 32611, footprint_m=fp)
    assert pc.meta["project"] == "old_2016" and pc.meta["fallback_used"] is True
