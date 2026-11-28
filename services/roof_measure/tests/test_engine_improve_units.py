"""Unit tests of the phase 2b pieces: plane-island dropping, flat-roof junk absorption."""

import numpy as np
from shapely.geometry import Polygon, box

from roof_measure.engine.errors import Ctx
from roof_measure.engine.grow import drop_islands
from roof_measure.engine.junk import absorb_flat_junk
from roof_measure.engine.params import DEFAULT

PLANES = [np.array([0.0, 0.0, 3.0])]


def _grid(x0, x1, y0, y1, step=0.3, noise=0.0):
    xs, ys = np.meshgrid(np.arange(x0, x1, step), np.arange(y0, y1, step))
    z = 3.0 + noise * np.random.default_rng(3).standard_normal(xs.size)
    return np.c_[xs.ravel(), ys.ravel(), z]


def test_drop_islands_removes_a_small_blob_far_from_the_plane_body():
    body = _grid(0, 8, 0, 6)
    blob = _grid(10.5, 11.5, 2, 3, noise=0.09)  # 16 scattered points (a tree crown), 2.5 m from the body
    pts = np.vstack([body, blob])
    lab = np.zeros(len(pts), int)
    out = drop_islands(pts, lab, PLANES, DEFAULT)
    assert (out[: len(body)] == 0).all() and (out[len(body):] == -1).all()


def test_drop_islands_keeps_a_handful_of_strays():
    """Four points at a crease that fit the plane are not a crown (and a roof's creases are full of them)."""
    body = _grid(0, 8, 0, 6)
    strays = _grid(10.5, 11.5, 2, 2.4, noise=0.02)
    pts = np.vstack([body, strays])
    assert len(strays) < DEFAULT.assign_island_min_pts
    assert (drop_islands(pts, np.zeros(len(pts), int), PLANES, DEFAULT) == 0).all()


def test_drop_islands_keeps_a_big_separate_part_of_the_same_plane():
    body = _grid(0, 8, 0, 6)
    wing = _grid(10.5, 14, 0, 4)  # 4 x 3.5 m of the same plane: a real second part (dozens of points)
    pts = np.vstack([body, wing])
    out = drop_islands(pts, np.zeros(len(pts), int), PLANES, DEFAULT)
    assert (out == 0).all()


def test_drop_islands_leaves_a_connected_plane_alone():
    pts = _grid(0, 6, 0, 6)
    assert (drop_islands(pts, np.zeros(len(pts), int), PLANES, DEFAULT) == 0).all()


def test_flat_junk_is_absorbed_into_the_flat_neighbour():
    planes = [np.array([0.0, 0.0, 3.0]), np.array([0.0, 0.0, 4.0]), np.array([0.3, 0.0, 3.0])]
    items = [[0, box(0, 0, 10, 8).difference(box(8, 0, 10, 2))], [1, box(8, 0, 10, 2)]]  # a 4 m2 unit on a platform, against the flat roof
    out, n = absorb_flat_junk(items, planes, Ctx(DEFAULT, None))
    assert n == 1 and len(out) == 1 and abs(out[0][1].area - 80.0) < 1e-3


def test_a_small_facet_between_pitched_roofs_is_not_junk():
    planes = [np.array([0.0, 0.5, 3.0]), np.array([0.0, -0.5, 9.0]), np.array([0.4, 0.0, 3.0])]
    items = [[0, box(0, 0, 10, 4)], [1, box(0, 4, 10, 8)], [2, Polygon([(10, 2), (12, 2), (12, 4), (10, 4)])]]  # a 4 m2 hip end
    out, n = absorb_flat_junk(items, planes, Ctx(DEFAULT, None))
    assert n == 0 and len(out) == 3


def test_a_flat_facet_over_the_size_limit_stays():
    planes = [np.array([0.0, 0.0, 3.0]), np.array([0.0, 0.0, 4.0])]
    items = [[0, box(0, 0, 10, 8).difference(box(6, 0, 10, 4))], [1, box(6, 0, 10, 4)]]  # 16 m2 platform: a real level
    out, n = absorb_flat_junk(items, planes, Ctx(DEFAULT, None))
    assert n == 0 and len(out) == 2


def test_a_sub_millimetre_pinch_does_not_become_a_self_intersecting_ring_in_the_result():
    """Rounding the ring to the millimetre folded a 0.4 mm pinch into a bow-tie (9 of 160 tuning houses had one)."""
    from roof_measure.engine.result_json import _ring

    pinch = Polygon([(0, 0), (4, 0), (4, 3), (2.0004, 3), (2.0004, 3.0004), (1.9996, 3.0004), (1.9996, 3), (0, 3)])
    assert pinch.is_valid
    ring = _ring(pinch)
    assert Polygon(ring).is_valid and abs(Polygon(ring).area - pinch.area) < 0.01


def test_close_gaps_gives_a_thin_channel_to_a_neighbour_and_leaves_a_hole():
    from roof_measure.engine.cleanup import close_gaps

    outline = box(0, 0, 10, 8)
    items = [[0, box(0, 0, 4.9, 8)], [1, box(5.1, 0, 10, 8)]]  # a 0.2 m channel between two facets
    out, n = close_gaps(items, outline, DEFAULT)
    assert n == 1 and abs(sum(g.area for _, g in out) - 80.0) < 0.1
    items = [[0, box(0, 0, 3, 8)], [1, box(6, 0, 10, 8)]]  # a 3 m wide hole is not a channel
    assert close_gaps(items, outline, DEFAULT)[1] == 0


def _flat_pair_points(tilt_b: float):
    rng = np.random.default_rng(2)
    xa, ya = rng.uniform(0, 5, 400), rng.uniform(0, 8, 400)
    xb, yb = rng.uniform(5, 10, 400), rng.uniform(0, 8, 400)
    za = 3.0 + rng.normal(0, 0.03, 400)
    zb = 3.0 + tilt_b * (xb - 5) + rng.normal(0, 0.03, 400)
    return np.r_[np.c_[xa, ya, za], np.c_[xb, yb, zb]]


def test_flat_facets_merge_only_when_one_plane_keeps_the_fit():
    from roof_measure.engine.junk import merge_flat_fitting

    items = [[0, box(0, 0, 5, 8)], [1, box(5, 0, 10, 8)]]
    same = merge_flat_fitting(items, [np.array([0.0, 0.0, 3.0]), np.array([0.0, 0.0, 3.0])], _flat_pair_points(0.0), Ctx(DEFAULT, None))
    assert same[1] == 1 and len(same[0]) == 1
    # a drainage tilt of 1.8/12 beside a level membrane: one plane would lose the fit, so both stay
    planes = [np.array([0.0, 0.0, 3.0]), np.array([0.15, 0.0, 3.0 - 0.75])]
    tilted = merge_flat_fitting(items, planes, _flat_pair_points(0.15), Ctx(DEFAULT, None))
    assert tilted[1] == 0 and len(tilted[0]) == 2
