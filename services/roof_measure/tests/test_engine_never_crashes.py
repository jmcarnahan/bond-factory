"""Bad input never crashes the engine: a refused result with a reason, or an EngineError subclass (never anything else)."""

import time

import numpy as np
import pytest
from engine_cases import inputs
from shapely.geometry import MultiPolygon, Point, Polygon, box

from roof_measure.engine import measure_roof
from roof_measure.engine.errors import EngineError, EngineTimeout
from roof_measure.engine.load import roof_points_from_arrays

WALL = box(0, 0, 12, 8)


def _measure(xyz, wall=WALL, **kw):
    rp = roof_points_from_arrays(np.asarray(xyz, float).reshape(-1, 3), wall if not wall.is_empty else box(0, 0, 1, 1))
    try:
        return measure_roof(rp, wall, outline_source="county", **kw)
    except EngineError as ex:  # the only exceptions allowed out
        assert not isinstance(ex, EngineTimeout) or "deadline" in str(ex)
        return ex


def _ok_or_refused(res):
    if isinstance(res, EngineError):
        return
    assert res.refused or res.facets
    if res.refused:
        assert res.quality.verdict and res.quality.reasons and res.facets == [] and res.edges == []
        out = res.to_result_json("x")
        assert out["facets"] == [] and out["diagnostics"]["quality"]["verdict"] == res.quality.verdict


def test_empty_points():
    res = _measure(np.zeros((0, 3)))
    assert res.refused and res.quality.verdict == "lidar_too_sparse"


def test_nan_and_inf_points_are_dropped_or_refused():
    rng = np.random.default_rng(0)
    xyz = np.c_[rng.uniform(0, 12, 400), rng.uniform(0, 8, 400), 3 + 0.2 * rng.uniform(0, 1, 400)]
    xyz[::7] = np.nan
    xyz[3::11, 2] = np.inf
    _ok_or_refused(_measure(xyz))
    _ok_or_refused(_measure(np.full((500, 3), np.nan)))


def test_three_points():
    res = _measure([[1, 1, 3], [5, 2, 3.2], [3, 6, 3.1]])
    assert res.refused


def test_collinear_points():
    t = np.linspace(0, 10, 600)
    res = _measure(np.c_[t, 0.5 * t, 3 + 0.01 * t])
    assert res.refused
    res = _measure(np.c_[np.full(600, 4.0), np.full(600, 3.0), np.linspace(2, 5, 600)])  # one column of points
    assert res.refused


def test_flat_noise_without_a_roof():
    rng = np.random.default_rng(1)
    xyz = np.c_[rng.uniform(-1, 13, 3000), rng.uniform(-1, 9, 3000), rng.uniform(0, 5, 3000)]  # a cloud, no planes
    _ok_or_refused(_measure(xyz))


def test_200k_points_are_thinned_deterministically():
    _, wall, pts = inputs("hip_d16")
    roof = pts[pts[:, 3] == 1][:, :3]
    rng = np.random.default_rng(2)
    reps = 200_000 // len(roof) + 1
    big = np.vstack([roof + rng.normal(0, 0.01, roof.shape) for _ in range(reps)])[:200_000]
    t0 = time.monotonic()
    a = _measure(big, wall)
    assert time.monotonic() - t0 < 60
    b = _measure(big, wall)
    assert not isinstance(a, EngineError) and a.diagnostics.get("thinned") is True
    assert not a.refused and len(a.facets) == 4
    assert a.to_result_json("x") == b.to_result_json("x")


@pytest.mark.parametrize("wall", [
    Polygon(), Polygon([(0, 0), (10, 0), (20, 0), (0, 0)]), Polygon([(0, 0), (1, 0), (1, 1)]),
    Polygon([(0, 0), (8, 8), (8, 0), (0, 8)]),  # a bow-tie (self-intersecting)
    MultiPolygon([box(0, 0, 1, 1), box(20, 20, 21, 21)]), Point(0, 0).buffer(0.01)])
def test_degenerate_outlines(wall):
    rng = np.random.default_rng(3)
    xyz = np.c_[rng.uniform(0, 12, 800), rng.uniform(0, 8, 800), 3 + 0.5 * rng.uniform(0, 1, 800)]
    rp = roof_points_from_arrays(xyz, box(0, 0, 12, 8))
    try:
        res = measure_roof(rp, wall, outline_source="county")
    except EngineError:
        return
    _ok_or_refused(res)


def test_a_non_polygon_footprint_and_wrong_shaped_points():
    rp, wall, _ = inputs("gable_d8")
    for bad in (None, Point(1, 1), "not a geometry"):
        try:
            res = measure_roof(rp, bad, outline_source="county")
        except EngineError:
            continue
        _ok_or_refused(res)
    rp.xyz = np.zeros((5, 2))
    _ok_or_refused(_measure_rp(rp, wall))


def _measure_rp(rp, wall):
    try:
        return measure_roof(rp, wall, outline_source="county")
    except EngineError as ex:
        return ex


def test_duplicate_points_and_a_single_repeated_point():
    _ok_or_refused(_measure(np.tile([3.0, 3.0, 4.0], (900, 1))))
    rng = np.random.default_rng(4)
    base = np.c_[rng.uniform(0, 12, 300), rng.uniform(0, 8, 300), 3 + 0.5 * rng.uniform(0, 1, 300)]
    _ok_or_refused(_measure(np.vstack([base, base, base])))


def test_a_deadline_that_expires_mid_run_raises_the_typed_timeout():
    rp, wall, pts = inputs("complex_hip_d16")
    with pytest.raises(EngineTimeout):
        measure_roof(rp, wall, deadline=time.monotonic() + 0.02, outline_source="county", context=pts)
