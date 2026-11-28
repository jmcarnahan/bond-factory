"""The pipeline: ``measure(...)`` runs the plane engine end to end on synthetic data (footprint chain and LiDAR stood in
by fakes), raises the job error codes, and never falls back to another engine."""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest
from engine_cases import case
from shapely import affinity
from shapely.geometry import Polygon

from roof_measure import cache, footprint, lidar, pipeline
from roof_measure.footprint_types import Footprint, FootprintError
from roof_measure.frame import project_geometry
from roof_measure.library import MeasureError, measure
from roof_measure.version import PIPELINE_VERSION

EPSG = 32611
ORIGIN = (400000.0, 3750000.0)  # metres in the zone's grid: a synthetic spot, only ever used through pyproj
ADDR = "1 Example St, Sampletown, CA 90000"
MAIN_DX = (0.0, 0.0)
OTHER_DX = (60.0, 0.0)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(cache, "_send", boom)


def at(name: str, dx: tuple[float, float]) -> tuple[Polygon, np.ndarray]:
    """The wall polygon and the LiDAR points (x, y, z, class) of synthetic case ``name`` placed at ORIGIN + dx."""
    c = case(name)
    wall = affinity.translate(c.roof.wall_polygon(), ORIGIN[0] + dx[0], ORIGIN[1] + dx[1])
    pts = c.points().copy()
    pts[:, 0] += ORIGIN[0] + dx[0]
    pts[:, 1] += ORIGIN[1] + dx[1]
    return wall, pts


def cloud(pts: np.ndarray) -> lidar.PointCloud:
    return lidar.PointCloud(pts[:, 0], pts[:, 1], pts[:, 2], pts[:, 3].astype(np.uint8), np.zeros(len(pts)),
                            {"project": "synthetic", "year": 2023, "epsg": EPSG})


class World:
    """What the fakes serve: a main building and optionally another on the same parcel."""

    def __init__(self, main="gable_d8", other=None, thin=1, shift=(0.0, 0.0), clutter=0, pitch=None):
        self.main_wall, self.main_pts = at(main, MAIN_DX)
        if pitch is not None:  # a gable of this pitch instead of a named case
            from roof_measure.engine import synth_points

            roof = synth_points.gable(pitch=pitch)
            self.main_wall = affinity.translate(roof.wall_polygon(), *ORIGIN)
            self.main_pts = synth_points.simulate(roof, density=8, seed=3) + np.array([ORIGIN[0], ORIGIN[1], 0.0, 0.0])
        if shift != (0.0, 0.0):  # the roof points lie off the footprint: the outline is somebody else's
            self.main_pts = self.main_pts + np.array([shift[0], shift[1], 0.0, 0.0])
        if clutter:  # random returns over the roof at random heights: no plane explains them
            rng = np.random.default_rng(5)
            minx, miny, maxx, maxy = self.main_wall.bounds
            junk = np.c_[rng.uniform(minx, maxx, clutter), rng.uniform(miny, maxy, clutter), rng.uniform(3.2, 7.0, clutter),
                         np.ones(clutter)]
            self.main_pts = np.vstack([self.main_pts, junk])
        self.other_wall, self.other_pts = at(other, OTHER_DX) if other else (None, None)
        self.thin = thin
        self.fetches: list[tuple[float, float]] = []

    def wgs(self, poly: Polygon) -> Polygon:
        return project_geometry(poly, EPSG, 4326)

    def point(self) -> tuple[float, float]:
        c = self.wgs(self.main_wall).representative_point()
        return c.y, c.x

    def fp(self, *a, **k) -> Footprint:
        others = [self.wgs(self.other_wall)] if self.other_wall is not None else []
        return Footprint(provider="lacounty_lariac_2020", id="B1", polygon_wgs84=self.wgs(self.main_wall), height_ft=None,
                         area_sqft=self.main_wall.area * 10.7639, parcel_id="P1", other_buildings=others,
                         other_info=[{"id": "B2", "area_sqft": self.other_wall.area * 10.7639}] if others else [],
                         match="exact", source="lariac")

    def lidar(self, fp_m: Polygon, epsg: int) -> lidar.PointCloud:
        c = fp_m.centroid
        near_main = c.distance(self.main_wall.centroid) < 5.0
        pts = self.main_pts if near_main else self.other_pts
        self.fetches.append((round(c.x), round(c.y)))
        return cloud(pts[:: self.thin])


@pytest.fixture
def world(monkeypatch):
    def make(**kw):
        w = World(**kw)
        monkeypatch.setattr(footprint, "fetch_footprint", w.fp)
        monkeypatch.setattr(lidar, "fetch_for_footprint", w.lidar)
        return w
    return make


def run(w: World, tmp_path, **kw):
    lat, lng = w.point()
    args = {"method": "auto", "cache_dir": tmp_path / "cache", "isolate": False}
    return measure(ADDR, lat=lat, lng=lng, **(args | kw))


def test_the_plane_engine_returns_a_full_envelope(world, tmp_path):
    w = world(main="flat_pitched_step_d8")
    stages: list[str] = []
    env = run(w, tmp_path, on_stage=stages.append)
    assert env["contract"] == "bond.roof_model/0.2" and env["pipeline_version"] == PIPELINE_VERSION == "0.5.1"
    assert env["method_used"] == "lidar_skeleton" and env["footprint_source"] == "lariac"
    assert env["verification"]["verdict"] == "unverified"
    m, t = env["model"], env["totals"]
    from roof_measure.engine.params import DEFAULT

    assert m["quality"]["engine"] == "planes/1" and m["quality"]["verdict"] == "ok" and m["quality"]["parcel_match"] == "exact"
    assert m["quality"]["engine_params"] == DEFAULT.stable_hash() and "tree_cover_pct" in m["quality"] and "fit_clear" in m["quality"]
    assert m["source"]["building"]["parcel_id"] == "P1" and m["source"]["building"]["outline_id"] == "B1"
    assert m["source"]["lidar"]["density_per_m2"] >= 6 and m["source"]["footprint"]["provider"].startswith("lacounty")
    for k in ("planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "ridge_cap_ridge_hip_ft",
              "roofing_flat_sqft", "roofing_pitched_sqft", "area_sqft_wall_line", "area_sqft_roof_edge", "complexity"):
        assert k in t, k
    assert t["roofing_flat_sqft"] > 100 and t["roofing_pitched_sqft"] > 100
    assert t["area_sqft_wall_line"] <= t["planes_surface_area_sqft"] == t["area_sqft_roof_edge"]
    assert m["totals"]["lengths_ft"]["level_change"] > 0 and m["planes"] and "model_from_planes" not in env["warning_codes"]
    assert "lidar" in stages and "model" in stages and "blocks" not in stages
    json.dumps(env, allow_nan=False)


def test_nearby_buildings_reach_the_envelope_for_a_county_footprint_and_only_then(world, tmp_path, monkeypatch):
    w = world()
    rows = [{"outline_id": "N1", "area_sqft": 410.0, "distance_m": 12.5, "on_matched_parcel": True}]
    base_fp = w.fp
    monkeypatch.setattr(footprint, "fetch_footprint", lambda *a, **k: dataclasses.replace(base_fp(), nearby=rows))
    assert run(w, tmp_path)["nearby_buildings"] == rows
    monkeypatch.setattr(footprint, "fetch_footprint", lambda *a, **k: dataclasses.replace(base_fp(), nearby=[]))
    assert run(w, tmp_path / "b")["nearby_buildings"] == []  # present and empty: the county was asked, nothing stands near
    monkeypatch.setattr(footprint, "fetch_footprint", lambda *a, **k: dataclasses.replace(base_fp(), source="osm", provider="osm"))
    assert "nearby_buildings" not in run(w, tmp_path / "c")


def test_the_work_dir_keeps_the_model_and_the_engine_result(world, tmp_path):
    w = world()
    work = tmp_path / "work"
    run(w, tmp_path, work_dir=work)
    files = sorted(p.name for p in work.iterdir())
    assert any(f.endswith("_model.json") for f in files) and any(f.endswith("_engine.json") for f in files)


def test_low_density_becomes_a_warning_with_its_code(world, tmp_path):
    w = world(main="gable_d16", thin=3)  # a third of 16 per m2: about 5 on the roof
    env = run(w, tmp_path)
    assert env["model"]["quality"]["verdict"] == "low_density" and "low_density" in env["warning_codes"]
    assert "low_density" in env["model"]["quality"]["reasons"]
    assert "outline_mismatch" not in env["warning_codes"] and "poor_fit" not in env["warning_codes"]


def test_outline_mismatch_becomes_a_warning_with_its_code(world, tmp_path):
    w = world(shift=(3.5, 0.0))  # the roof points sit 3.5 m beside the outline (shift ratio about 0.35)
    env = run(w, tmp_path)
    q = env["model"]["quality"]
    assert "outline_mismatch" in q["reasons"] and "outline_mismatch" in env["warning_codes"]
    assert q["outline_shift"] >= 0.17 or q["outline_covered_pct"] < 70


def test_poor_fit_becomes_a_warning_with_its_code(world, tmp_path):
    w = world(clutter=1400)  # more unexplained returns than roof returns
    env = run(w, tmp_path)
    q = env["model"]["quality"]
    assert q["fit_all"] < 0.55 and "poor_fit" in q["reasons"] and "poor_fit" in env["warning_codes"]


def test_a_borderline_low_slope_roof_gets_the_low_slope_confirm_warning(world, tmp_path):
    w = world(pitch=2.0)
    env = run(w, tmp_path)
    assert env["totals"]["low_slope_confirm_sqft"] > 0 and "low_slope_confirm" in env["warning_codes"]
    assert "low_slope_confirm" in env["model"]["quality"]["reasons"]
    assert any(f["borderline"] for f in env["model"]["facets"])
    clean = run(world(), tmp_path)
    assert "low_slope_confirm" not in clean["warning_codes"] and clean["totals"]["low_slope_confirm_sqft"] == 0


def test_under_four_points_per_m2_is_refused_with_lidar_too_sparse(world, tmp_path):
    w = world(main="gable_d16", thin=5)  # about 3 per m2
    with pytest.raises(MeasureError) as ei:
        run(w, tmp_path)
    assert ei.value.code == "lidar_too_sparse" and "points/m2" in ei.value.message


def test_no_footprint_and_an_expired_deadline_keep_their_codes(world, monkeypatch, tmp_path):
    w = world()

    def nothing(*a, **k):
        raise FootprintError("nothing here")
    monkeypatch.setattr(footprint, "fetch_footprint", nothing)
    with pytest.raises(MeasureError) as ei:
        run(w, tmp_path)
    assert ei.value.code == "no_footprint"
    monkeypatch.setattr(footprint, "fetch_footprint", w.fp)

    def slow(fp_m, epsg):
        import time

        time.sleep(0.05)
        return w.lidar(fp_m, epsg)
    monkeypatch.setattr(lidar, "fetch_for_footprint", slow)
    with pytest.raises(MeasureError) as ei:
        run(w, tmp_path, deadline_s=0.01)
    assert ei.value.code == "timeout"


def test_an_engine_failure_is_measurement_failed(world, monkeypatch, tmp_path):
    from roof_measure.engine import errors as eng_errors

    w = world()
    import roof_measure.engine as engine_pkg

    def boom(*a, **k):
        raise eng_errors.EngineFailure("RuntimeError: broken")
    monkeypatch.setattr(engine_pkg, "measure_roof", boom)
    with pytest.raises(MeasureError) as ei:
        run(w, tmp_path)
    assert ei.value.code == "measurement_failed"


def test_an_engine_refusal_is_reported_not_swallowed(world, monkeypatch, tmp_path):
    from roof_measure.engine import measure as eng_measure
    from roof_measure.engine.params import DEFAULT

    w = world()
    import roof_measure.engine as engine_pkg

    monkeypatch.setattr(engine_pkg, "measure_roof", lambda *a, **k: eng_measure.refused("bad_points", DEFAULT))
    with pytest.raises(MeasureError) as ei:
        run(w, tmp_path)
    assert ei.value.code == "no_lidar_coverage"


def test_arguments_the_engine_cannot_serve_are_refused_up_front(tmp_path):
    kw = {"cache_dir": tmp_path / "c", "isolate": False, "lat": 1.0, "lng": 2.0}
    with pytest.raises(ValueError, match="engine must be"):
        measure(ADDR, engine="skeleton", **kw)
    with pytest.raises(ValueError, match="method must be"):
        measure(ADDR, method="lidar_agent", **kw)
    with pytest.raises(pipeline.PipelineError):
        pipeline.run_pipeline(ADDR, tmp_path, "lidar_agent")


# ----------------------------------------------------------------------------- the other buildings on the lot
def test_other_buildings_are_measured_with_the_same_engine(world, tmp_path):
    w = world(main="gable_d8", other="flat_d8")
    env = run(w, tmp_path, include_other_buildings=True)
    other = env["other_buildings"]
    assert len(other) == 1 and other[0]["status"] == "ok" and other[0]["error_code"] is None
    assert other[0]["model"]["quality"]["engine"] == "planes/1" and other[0]["totals"]["roofing_flat_sqft"] > 100
    assert other[0]["offset_ft"][0] == pytest.approx(60.0 / 0.3048, abs=3.0)  # the origins are 60 m apart (bbox corners differ a little)
    assert env["totals"]["lot_buildings"] == 2 and len(w.fetches) == 2


def test_an_other_building_that_cannot_be_measured_fails_alone(world, tmp_path):
    w = world(main="gable_d8", other="flat_d8")
    w.other_pts = w.other_pts[::6]  # too thin for the second building only
    env = run(w, tmp_path, include_other_buildings=True)
    assert env["other_buildings"][0]["status"] == "failed" and env["other_buildings"][0]["error_code"] == "lidar_too_sparse"
    assert env["model"]["quality"]["engine"] == "planes/1"


# ----------------------------------------------------------------------------- the removed arguments
def test_engine_planes_is_accepted_and_no_verifier_runs(world, tmp_path):
    w = world()
    env = run(w, tmp_path, engine="planes")
    assert env["verification"]["verdict"] == "unverified" and env["verification"]["skipped"] == "engine"
    assert env["verification"]["rounds"] == 0 and env["verification"]["usage"] == {"input_tokens": 0, "output_tokens": 0}
    assert "verifier_unverified" not in env["warning_codes"]  # nothing was meant to verify an engine result
    assert env["model"]["quality"]["engine"] == "planes/1"


def test_model_origin_carries_the_epsg_and_projects_back_to_the_frame_origin(world, tmp_path):
    """model.origin {lat, lng, epsg}: projecting lat/lng with that EPSG gives the south-west corner of the footprint's
    bounding box, which is [0, 0] ft of the model (within 1 cm), so a WGS84 point can be moved into the model's feet."""
    from pyproj import Transformer

    w = world()
    env = run(w, tmp_path)
    o = env["model"]["origin"]
    assert o["epsg"] == EPSG
    x, y = Transformer.from_crs(4326, o["epsg"], always_xy=True).transform(o["lng"], o["lat"])
    minx, miny, _, _ = w.main_wall.bounds
    assert abs(x - minx) < 0.01 and abs(y - miny) < 0.01
