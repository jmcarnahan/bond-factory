"""A small facet whose returns are not on its plane is not a roof plane of its own (slice c, tree / clutter facets).

Unit geometry (written before any run): plane A = 0.5 x and plane B = 6 - 0.5 x meet along x = 6. The big facet of B is x in
6..12, y in 0..6 (36 m2, never judged); the facet under test sits at x in 3..6, y in 0..3 (9 m2, under the 12 m2 limit) and
is labelled A. Returns lie on a regular 0.35 m grid, noise free. Where the returns lie on B, A's residual is 6 - x: a median of
1.5 m over x in 3..6, far over the 0.35 m cut; where they lie on A the residual is 0."""

from __future__ import annotations

import numpy as np
import pytest
from shapely.geometry import box

from roof_measure.engine.cleanup import merge_off_plane_facets
from roof_measure.engine.errors import Ctx
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.measure import measure_stages
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.synth_points import SHAPES, SynthCase

A = np.array([0.5, 0.0, 0.0])
B = np.array([-0.5, 0.0, 6.0])
STEP = 0.35


def _grid(x0, x1, y0, y1, plane, off=0.0):
    xs, ys = np.meshgrid(np.arange(x0 + STEP / 2, x1, STEP), np.arange(y0 + STEP / 2, y1, STEP))
    x, y = xs.ravel(), ys.ravel()
    return np.c_[x, y, plane[0] * x + plane[1] * y + plane[2] + off]


def _items(small=(3.0, 6.0, 0.0, 3.0)):
    x0, x1, y0, y1 = small
    return [[0, box(x0, y0, x1, y1)], [1, box(6.0, 0.0, 12.0, 6.0)], [1, box(3.0, 3.0, 6.0, 6.0)]]


def _run(items, returns, params=DEFAULT):
    return merge_off_plane_facets(items, [A, B], returns, Ctx(params, None))


def test_a_small_facet_whose_returns_lie_on_a_neighbours_plane_is_merged_and_its_area_kept():
    items, n = _run(_items(), _grid(0.0, 12.0, 0.0, 6.0, B))
    assert n == 1 and [lab for lab, _ in items] == [1, 1]
    assert abs(sum(p.area for _, p in items) - 54.0) < 0.1


def test_returns_that_are_on_no_plane_at_all_also_merge_it():
    """Canopy: the returns inside the facet are 2 m above every roof plane (the roof's own returns are not there)."""
    returns = np.vstack([_grid(6.0, 12.0, 0.0, 6.0, B), _grid(3.0, 6.0, 3.0, 6.0, B), _grid(3.0, 6.0, 0.0, 3.0, A, off=2.0)])
    _, n = _run(_items(), returns)
    assert n == 1


def test_a_facet_on_its_own_plane_is_kept():
    returns = np.vstack([_grid(3.0, 6.0, 0.0, 3.0, A), _grid(6.0, 12.0, 0.0, 6.0, B), _grid(3.0, 6.0, 3.0, 6.0, B)])
    assert _run(_items(), returns)[1] == 0


def test_a_few_stray_returns_do_not_move_the_median():
    returns = np.vstack([_grid(3.0, 6.0, 0.0, 3.0, A), _grid(6.0, 12.0, 0.0, 6.0, B)])
    returns[::5, 2] += 1.0  # 20% of the returns 1 m high: the median residual stays 0
    assert _run(_items(), returns)[1] == 0


@pytest.mark.parametrize("small", [(0.0, 6.0, 0.0, 3.0)], ids=["18 m2 facet"])
def test_a_facet_over_the_small_limit_is_never_judged(small):
    assert _run(_items(small), _grid(0.0, 12.0, 0.0, 6.0, B))[1] == 0


def test_a_facet_with_fewer_returns_than_a_plane_needs_is_not_judged():
    returns = np.vstack([_grid(6.0, 12.0, 0.0, 6.0, B), _grid(3.0, 6.0, 0.0, 3.0, B)[: DEFAULT.plane_min_pts - 1]])
    assert _run(_items(), returns)[1] == 0


def test_the_cut_is_a_parameter():
    assert _run(_items(), _grid(0.0, 12.0, 0.0, 6.0, B), DEFAULT.replace(off_plane_facet_mad_m=2.0))[1] == 0


def test_the_last_facet_is_never_merged():
    items, n = merge_off_plane_facets([[0, box(3.0, 0.0, 6.0, 3.0)]], [A, B], _grid(3.0, 6.0, 0.0, 3.0, B), Ctx(DEFAULT, None))
    assert n == 0 and len(items) == 1


# Two synthetic roofs where the engine without the rule keeps a tree-crown facet (one facet too many) and with it does not.
CANOPY = [("t_shape", 2, 8), ("cross_gable", 3, 4)]


@pytest.mark.parametrize(("shape", "trees", "seed"), CANOPY)
def test_a_canopy_over_an_eave_does_not_leave_a_facet_of_its_own(shape, trees, seed):
    c = SynthCase(f"{shape}_canopy", SHAPES[shape](), {"density": 8, "seed": seed, "trees": trees})
    pts = c.points()
    wall = c.roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)

    def run(params):
        res, _ = measure_stages(rp, wall, params=params, deadline=None, outline_source="county", parcel_match="given", context=pts)
        return res

    off = run(DEFAULT.replace(off_plane_facet_mad_m=99.0))
    on = run(DEFAULT)
    assert len(off.facets) == len(c.roof.facets) + 1  # today's engine without the rule: the crown is a facet
    assert len(on.facets) == len(c.roof.facets)
    assert on.diagnostics["off_plane_facets_merged"] == 1
    assert abs(sum(f.plan_area_sqft for f in on.facets) - sum(f.plan_area_sqft for f in off.facets)) < 1.0  # merged, not dropped
