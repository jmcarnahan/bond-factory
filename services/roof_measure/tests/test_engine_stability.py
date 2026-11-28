"""The partition does not change when the building outline moves by centimetres (slice c of the roof-accuracy plan).

Limits, written before the first run (from the geometry of the roofs, never from output):

* the wall polygon buffered by +0.1 m and -0.1 m (mitre) and shifted 0.2 m in x and in y is a county outline that is
  wrong by up to 20 cm; the roof, the points and the exact answer do not move;
* the facet count must not change (a facet is a plane the roof has or has not);
* ridge + hip and valley may change by at most ``max(2 ft, 1.5 % of the roof's ridge + hip + valley)``: moving every
  eave 0.1 m (0.33 ft) lengthens each hip or valley that ends on an eave by up to 0.1 m x sqrt(2) = 0.46 ft, and a
  roof has about one such line end per 10 ft of hip and valley; 1.5 % of the total is that allowance, and 2 ft is the
  floor for a small roof (the brief's limit).
"""

from __future__ import annotations

import numpy as np
import pytest
import shapely
from shapely import affinity

from roof_measure.engine.errors import Ctx
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.measure import measure_stages
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.raster import label_raster
from roof_measure.engine.synth_points import cases

# Roofs that do NOT hold yet. Each entry is a strict xfail: the slice that fixes the named cause must delete the entry.
KNOWN = {
    "complex_hip_d8": "small-facet threshold without hysteresis (cleanup.merge_small_facets / _keeps_small): a 3.4-4.8 m2 hip porch is "
                      "kept or merged away by 0.1 m of outline, 19 or 20 facets and ridge+hip +-5 ft",
    "l_shape_d8_trees": "edge typing from polluted jump points (edges.py, 'jump before plane logic'): the facets are identical but a 7.7 ft hip "
                        "is typed level_change 4.8 ft in one run (ridge+hip 84.1 vs 88.6); owner: slice B (typing)"}
HOLD = ["gable_d8", "hip_d8", "l_shape_d8", "t_shape_d8", "cross_gable_d8", "dutch_gable_d8", "gable_d8_trees", "hip_d8_trees",
        "hip_d8_rot17", "l_shape_d8_rot45"]
ROOFS = [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=KNOWN[n])) for n in KNOWN] + HOLD
MOVES = {"buffer+0.1": lambda w: w.buffer(0.1, join_style=2), "buffer-0.1": lambda w: w.buffer(-0.1, join_style=2),
         "shift x 0.2": lambda w: affinity.translate(w, 0.2, 0.0), "shift y 0.2": lambda w: affinity.translate(w, 0.0, 0.2)}
FLOOR_FT, SHARE = 2.0, 0.015


def _case(name: str):
    return {c.name: c for c in cases()}[name]


def _run(name: str, wall):
    c = _case(name)
    pts = c.points()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    return measure_stages(rp, wall, params=DEFAULT, deadline=None, outline_source="county", parcel_match="given", context=pts)


def _totals(res) -> tuple[float, float]:
    t = res.totals
    return float(t["ridge_hip_ft"]), float(t["valley_ft"])


@pytest.mark.parametrize("name", ROOFS)
def test_the_facets_and_the_line_lengths_hold_when_the_wall_moves(name):
    wall = _case(name).roof.wall_polygon()
    base, _ = _run(name, wall)
    rh0, val0 = _totals(base)
    limit = max(FLOOR_FT, SHARE * (rh0 + val0))
    for move, f in MOVES.items():
        res, _ = _run(name, f(wall))
        rh, val = _totals(res)
        assert len(res.facets) == len(base.facets), (move, len(res.facets), len(base.facets))
        assert abs(rh - rh0) <= limit, (move, "ridge+hip", rh, rh0, limit)
        assert abs(val - val0) <= limit, (move, "valley", val, val0, limit)


def _labelling_inputs(name: str):
    _res, st = _run(name, _case(name).roof.wall_polygon())
    ok = st.plab >= 0
    return st.outline, st.crop[ok], st.plab[ok], st.planes, st.run.origin[2], st.run.beta


def test_the_label_lattice_follows_the_points_not_the_frame():
    """Moving the points and the outline together moves the raster with them and changes no label (to float noise: at most
    1 cell in 1000, where two planes cost the same)."""
    outline, q, qlab, planes, h, beta = _labelling_inputs("hip_d8")
    ctx = Ctx(DEFAULT, None)
    a, org_a = label_raster(outline, q, qlab, planes, h, beta, ctx)
    d = np.array([0.037, 0.021])
    q2 = q.copy()
    q2[:, :2] += d
    b, org_b = label_raster(affinity.translate(outline, *d), q2, qlab, planes, h, beta, ctx)
    # the planes are (a, b, c) of z = a x + b y + c: a shifted frame changes c only
    assert a.shape == b.shape
    assert np.mean(a != b) <= 0.001
    assert np.allclose(np.array(org_b[:2]) - np.array(org_a[:2]), d, atol=1e-9)


def test_labels_deep_inside_the_outline_do_not_depend_on_where_the_outline_edge_is():
    outline, q, qlab, planes, h, beta = _labelling_inputs("l_shape_d8")
    ctx = Ctx(DEFAULT, None)
    base, org = label_raster(outline, q, qlab, planes, h, beta, ctx)
    ny, nx = base.shape
    gx, gy = np.meshgrid(org[0] + (np.arange(nx) + 0.5) * h, org[1] + (np.arange(ny) + 0.5) * h)
    deep = shapely.contains_xy(outline.buffer(-0.6), gx, gy)
    for d in (0.1, -0.1):
        moved, org2 = label_raster(outline.buffer(d, join_style=2), q, qlab, planes, h, beta, ctx)
        assert org2 == org  # the lattice is the points', not the outline's
        assert moved.shape == base.shape
        assert np.mean(moved[deep] != base[deep]) <= 0.005, d  # the data cost reaches 1.2 m: only the edge cells may differ
