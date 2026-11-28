"""Bad LiDAR never crashes the engine path end to end: ``pipeline_engine.measure_points`` plus the adapter either give a
valid roof model or raise one of the pipeline's own errors (the codes ``lidar_too_sparse``, ``no_lidar_coverage``,
``no_footprint``, ``timeout``, ``measurement_failed``), never anything else. Extends test_engine_never_crashes through
the adapter (empty, NaN, collinear, 3 points, 200 000 points, an expired deadline)."""

from __future__ import annotations

import time

import numpy as np
from shapely.geometry import MultiPolygon, Polygon, box

from roof_measure import errors, lidar, pipeline_engine
from roof_measure.blockset import BlockSet
from roof_measure.deadline import Deadline, DeadlineExceeded
from roof_measure.engine import adapter
from roof_measure.footprint_types import FootprintError
from roof_measure.frame import Frame
from roof_measure.model import ModelError, validate

FRAME = Frame(epsg=32611, x0_m=0.0, y0_m=0.0, origin_lat=0.0, origin_lng=0.0)
WALL = box(0, 0, 12, 8)
ALLOWED = (lidar.LidarError, FootprintError, DeadlineExceeded, ModelError)
CODES = {"lidar_too_sparse", "no_lidar_coverage", "no_footprint", "timeout", "measurement_failed"}


def base() -> BlockSet:
    return BlockSet(address={"formatted": "x"}, origin={"lat": 0.0, "lng": 0.0}, frame={}, footprint_ft=[],
                    footprint_meta={"provider": "lacounty_lariac_2020", "id": "T", "area_sqft": 1000.0})


def cloud(xyz: np.ndarray, ground: bool = True) -> lidar.PointCloud:
    xyz = np.asarray(xyz, float).reshape(-1, 3)
    cls = np.ones(len(xyz))
    if ground:  # a ring of ground returns round the building, as the survey has
        rng = np.random.default_rng(0)
        g = np.c_[rng.uniform(-6, 18, 300), rng.uniform(-6, 14, 300), np.zeros(300)]
        xyz, cls = np.vstack([xyz, g]), np.r_[cls, np.full(300, 2.0)]
    return lidar.PointCloud(xyz[:, 0], xyz[:, 1], xyz[:, 2], cls.astype(np.uint8), np.zeros(len(xyz)), {"project": "p", "year": 2023})


def go(pts, wall=WALL, deadline_s=60.0, ground=True):
    """(model | exception): the whole engine path on a point cloud."""
    try:
        res, g, meta = pipeline_engine.measure_points(cloud(pts, ground), wall, FRAME, base(), deadline=Deadline.after(deadline_s))
        b = base()
        b.lidar = meta
        model = adapter.engine_model(res, b, g)
        validate(model)
        return model
    except ALLOWED as ex:
        assert errors.code_for(ex) in CODES, type(ex).__name__
        return ex


def roof(n: int, seed: int = 0, tilt: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x, y = rng.uniform(0, 12, n), rng.uniform(0, 8, n)
    return np.c_[x, y, 5.0 + tilt * y + rng.normal(0, 0.02, n)]


def test_a_good_cloud_is_the_control():
    out = go(roof(1200, tilt=0.4))
    assert isinstance(out, dict) and out["facets"]


def test_empty_nan_and_inf_clouds():
    assert isinstance(go(np.zeros((0, 3))), lidar.LidarTooSparse)
    xyz = roof(900)
    xyz[::7] = np.nan
    xyz[3::11, 2] = np.inf
    go(xyz)
    assert isinstance(go(np.full((500, 3), np.nan)), ALLOWED)


def test_three_points_and_collinear_points():
    assert isinstance(go([[1, 1, 5], [5, 2, 5.2], [3, 6, 5.1]]), ALLOWED)
    t = np.linspace(0, 10, 600)
    assert isinstance(go(np.c_[t, 0.5 * t, 5 + 0.01 * t]), ALLOWED)
    assert isinstance(go(np.c_[np.full(600, 4.0), np.full(600, 3.0), np.linspace(4, 8, 600)]), ALLOWED)


def test_two_hundred_thousand_points_are_thinned_and_measured():
    t0 = time.monotonic()
    out = go(roof(200_000, seed=2, tilt=0.35), deadline_s=120.0)
    assert isinstance(out, dict) and out["facets"] and time.monotonic() - t0 < 120


def test_an_expired_deadline_is_a_timeout_not_a_crash():
    out = go(roof(1500), deadline_s=0.0)
    assert isinstance(out, DeadlineExceeded) and errors.code_for(out) == "timeout"


def test_a_degenerate_footprint_is_no_footprint_or_a_valid_model():
    for wall in (Polygon(), box(0, 0, 0.01, 0.01), Polygon([(0, 0), (4, 0), (4, 4), (0, 4), (2, -3)]).buffer(0),
                 MultiPolygon([box(0, 0, 3, 3), box(20, 20, 24, 24)])):
        out = go(roof(900), wall)
        assert isinstance(out, (dict, *ALLOWED))


def test_points_nowhere_near_the_building_are_too_sparse():
    far = roof(2000) + np.array([500.0, 500.0, 0.0])
    assert isinstance(go(far), lidar.LidarTooSparse)
