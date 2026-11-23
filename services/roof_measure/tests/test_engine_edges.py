"""The engine's one edge typer (``roof_measure.engine.edges``): typing rules on hand-built facets, and exact synthetic
roofs through the typer (exact facets in: lengths per type within 1%, level-change jumps within 0.15 m), cross-checked
against the harness's independent recomputation (tools.roof_eval.edges_re)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from engine_cases import _cases, case
from shapely.geometry import Polygon

from roof_measure.engine.edges import build_edges, coplanar_seams, edge_diagnostics
from roof_measure.engine.errors import Ctx
from roof_measure.engine.params import DEFAULT
from roof_measure.engine.plane_math import aspect_deg
from roof_measure.engine.types import Facet

M2FT = 1 / 0.3048
CTX = Ctx(DEFAULT, None)
TYPES = ("eave", "rake", "ridge", "hip", "valley", "flat_edge", "level_change", "transition")


def facet(fid: str, ring, plane, points: int = 0) -> Facet:
    a, b, _c = plane
    g = math.hypot(a, b)
    return Facet(id=fid, polygon=Polygon(ring), plane=tuple(plane), label=0, pitch_rise=12 * g,
                 aspect_deg=aspect_deg(plane) if g > 1e-3 else 0.0, roof_type="flat" if 12 * g < DEFAULT.flat_cut_rise else "pitched",
                 plan_area_sqft=0.0, area_sqft=0.0, points=points, rms_m=0.0)


def by_type(edges, *, exterior=None):
    out: dict[str, float] = {}
    for e in edges:
        if exterior is None or (len(e.facets) == 1) == exterior:
            out[e.type] = out.get(e.type, 0.0) + e.length_ft
    return out


def points_on(f: Facet, n: int = 400, seed: int = 0, offset: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    minx, miny, maxx, maxy = f.polygon.bounds
    xy = np.c_[rng.uniform(minx, maxx, 6 * n), rng.uniform(miny, maxy, 6 * n)]
    import shapely

    xy = xy[shapely.contains_xy(f.polygon, xy[:, 0], xy[:, 1])][:n]
    return np.c_[xy, f.plane[0] * xy[:, 0] + f.plane[1] * xy[:, 1] + f.plane[2] + offset]


# a 10 m x 10 m gable at 6/12 (gradient 0.5): lower slope y 0..5 rises to the ridge at y = 5, upper slope falls away
SOUTH = facet("f1", [(0, 0), (10, 0), (10, 5), (0, 5)], (0, 0.5, 3.0))
NORTH = facet("f2", [(0, 5), (10, 5), (10, 10), (0, 10)], (0, -0.5, 8.0))


def test_a_gable_has_a_ridge_two_eaves_and_four_rakes_with_3d_lengths():
    edges = build_edges([SOUTH, NORTH], None, CTX)
    t = by_type(edges)
    assert t["ridge"] == pytest.approx(10 * M2FT, rel=1e-3)
    assert t["eave"] == pytest.approx(20 * M2FT, rel=1e-3)
    assert t["rake"] == pytest.approx(4 * math.hypot(5, 2.5) * M2FT, rel=1e-3)  # slope length, not plan length
    assert set(t) == {"ridge", "eave", "rake"}
    assert not any(e.high_edge for e in edges)
    ridge = next(e for e in edges if e.type == "ridge")
    assert ridge.p0[2] == pytest.approx(5.5) and ridge.p1[2] == pytest.approx(5.5)


def test_the_high_side_of_a_lone_pitched_facet_is_a_rake_never_a_ridge():
    edges = build_edges([SOUTH], None, CTX)
    t = by_type(edges)
    assert "ridge" not in t and t["eave"] == pytest.approx(10 * M2FT, rel=1e-3)
    high = [e for e in edges if e.high_edge]
    assert len(high) == 1 and high[0].type == "rake"
    assert high[0].length_ft == pytest.approx(10 * M2FT, rel=1e-3)
    assert t["rake"] == pytest.approx((10 + 2 * math.hypot(5, 2.5)) * M2FT, rel=1e-3)


def test_a_flat_facets_outline_is_flat_edge():
    flat = facet("f1", [(0, 0), (8, 0), (8, 6), (0, 6)], (0, 0, 3.0))
    t = by_type(build_edges([flat], None, CTX))
    assert t == {"flat_edge": pytest.approx(28 * M2FT, rel=1e-3)}


def test_pitched_beside_flat_at_one_height_is_a_transition_and_a_step_is_a_level_change():
    flat = facet("f1", [(0, 0), (10, 0), (10, 4), (0, 4)], (0, 0, 3.0))
    slope = facet("f2", [(0, 4), (10, 4), (10, 9), (0, 9)], (0, 0.5, 1.0))  # z = 3.0 at y = 4: meets the flat at its height
    edges = build_edges([flat, slope], None, CTX)
    assert [e.type for e in edges if len(e.facets) == 2] == ["transition"]
    stepped = facet("f2", [(0, 4), (10, 4), (10, 9), (0, 9)], (0, 0.5, 1.6))  # 0.6 m higher at the line
    q = np.vstack([points_on(flat), points_on(stepped, seed=1)])
    edges = build_edges([flat, stepped], q, CTX)
    lc = [e for e in edges if e.type == "level_change"]
    assert len(lc) == 1 and lc[0].jump_ft == pytest.approx(0.6 * M2FT, abs=0.15 * M2FT)
    assert lc[0].length_ft == pytest.approx(10 * M2FT, rel=1e-3)
    assert lc[0].p0[2] == pytest.approx(3.0)  # the line runs at the lower roof's height


def test_a_plane_gap_the_points_do_not_show_is_not_a_level_change():
    """The jump is measured from the points on both sides: planes 0.5 m apart over points that agree are one surface."""
    a = facet("f1", [(0, 0), (6, 0), (6, 6), (0, 6)], (0, 0, 3.0))
    b = facet("f2", [(6, 0), (12, 0), (12, 6), (6, 6)], (0, 0, 3.5))
    q = np.vstack([points_on(a), points_on(b, seed=1, offset=-0.5)])  # both sets of points lie at z = 3.0
    edges = build_edges([a, b], q, CTX)
    assert not [e for e in edges if len(e.facets) == 2]
    assert "level_change" not in by_type(edges)


def test_a_real_jump_is_a_level_change_whatever_the_planes_say_at_the_line():
    a = facet("f1", [(0, 0), (6, 0), (6, 6), (0, 6)], (0, 0, 3.0))
    b = facet("f2", [(6, 0), (12, 0), (12, 6), (6, 6)], (0, 0, 3.0))  # planes agree ...
    q = np.vstack([points_on(a), points_on(b, seed=1, offset=0.8)])  # ... the points are 0.8 m apart
    lc = [e for e in build_edges([a, b], q, CTX) if e.type == "level_change"]
    assert len(lc) == 1 and lc[0].jump_ft == pytest.approx(0.8 * M2FT, abs=0.15 * M2FT)


def test_coplanar_facets_share_no_edge_are_reported_as_seams_and_collinear_pieces_merge():
    west = facet("w", [(0, 0), (4, 0), (4, 5), (0, 5)], (0, 0.5, 3.0))
    east = facet("e", [(4, 0), (10, 0), (10, 5), (4, 5)], (0, 0.5, 3.0))  # the same plane, cut by a line down the slope
    edges = build_edges([west, east, NORTH], None, CTX)
    assert not [e for e in edges if set(e.facets) == {"w", "e"}]
    assert sorted(len(e.facets) for e in edges if e.type == "eave") == [1, 1, 1]  # an edge keeps its facets
    split = facet("s", [(0, 0), (3, 0), (10, 0), (10, 5), (0, 5)], (0, 0.5, 3.0))  # a vertex in the middle of the eave
    eaves = [e for e in build_edges([split, NORTH], None, CTX) if e.type == "eave" and e.facets == ("s",)]
    assert len(eaves) == 1 and eaves[0].length_ft == pytest.approx(10 * M2FT, rel=1e-3)  # collinear pieces merge
    seams = coplanar_seams([west, east, NORTH], DEFAULT)
    assert seams == [{"facets": ["w", "e"], "length_ft": pytest.approx(5 * M2FT, abs=0.2)}]
    assert coplanar_seams([SOUTH, NORTH], DEFAULT) == []


def test_two_flat_facets_at_one_height_are_one_membrane_not_an_edge():
    a = facet("f1", [(0, 0), (5, 0), (5, 5), (0, 5)], (0, 0, 3.0))
    b = facet("f2", [(5, 0), (10, 0), (10, 5), (5, 5)], (0, 0, 3.0))
    t = by_type(build_edges([a, b], None, CTX))
    assert t == {"flat_edge": pytest.approx(30 * M2FT, rel=1e-3)}
    assert [s["facets"] for s in coplanar_seams([a, b], DEFAULT)] == [["f1", "f2"]]


def test_a_valley_beside_a_concave_facet_is_a_valley_not_a_hip():
    """T-shaped and cross-gable roofs: the main slope wraps round the cross wing, so the crease line of one valley,
    extended, runs through the main facet's far part. The slope test is local to the segment (a representative-point
    test typed half of these valleys as hips)."""
    for name in ("t_shape_d8", "cross_gable_d8"):
        c = case(name)
        pts = c.points()
        t = by_type(build_edges(exact_facets(c.roof), pts[pts[:, 3] == 1][:, :3], CTX))
        exact = sum(e.length_ft for e in c.roof.edges if e.type == "valley")
        assert exact > 20 and t["valley"] == pytest.approx(exact, rel=0.01) and "hip" not in t


# ----------------------------------------------------------------------------- exact synthetic roofs
def exact_facets(roof) -> list[Facet]:
    return [Facet(id=f"f{f.id}", polygon=f.polygon(), plane=f.plane, label=f.id, pitch_rise=f.pitch, aspect_deg=f.aspect_deg,
                  roof_type=f.roof_type, plan_area_sqft=f.plan_area_sqft, area_sqft=f.area_sqft, points=0, rms_m=0.0)
            for f in roof.facets]


NAMES = [n for n in _cases() if n.endswith(("_d16", "_d8"))]


@pytest.mark.parametrize("name", NAMES)
def test_exact_facets_give_exact_edges(name):
    c = case(name)
    pts = c.points()
    edges = build_edges(exact_facets(c.roof), pts[pts[:, 3] == 1][:, :3], CTX)
    got, want = by_type(edges), {}
    for e in c.roof.edges:
        want[e.type] = want.get(e.type, 0.0) + e.length_ft
    for t in TYPES:
        a, b = got.get(t, 0.0), want.get(t, 0.0)
        assert abs(a - b) <= max(0.01 * b, 0.5), (t, a, b)
    exact_jumps = sorted(e.jump_ft for e in c.roof.edges if e.type == "level_change")
    jumps = sorted(e.jump_ft for e in edges if e.type == "level_change")
    assert len(jumps) == len(exact_jumps)
    for a, b in zip(jumps, exact_jumps, strict=True):
        assert abs(a - b) <= 0.15 * M2FT, (a, b)
    assert all(e.jump_ft is not None for e in edges if e.type == "level_change")
    assert all(e.jump_ft is None for e in edges if e.type != "level_change")


@pytest.mark.parametrize("name", [n for n in NAMES if n.endswith("_d8")])
def test_the_typer_agrees_with_the_harness_recomputation(name):
    """tools.roof_eval.edges_re types the same facets independently (geometry only); the two agree to 1% per type.
    The one convention that differs: the level high side of a lone pitched facet (the harness says eave, the contract
    rake), so eave and rake are compared together."""
    from tools.roof_eval import edges_re, geom

    c = case(name)
    pts = c.points()
    q = pts[pts[:, 3] == 1][:, :3]
    fs = exact_facets(c.roof)
    edges = build_edges(fs, q, CTX)
    res = {"facets": [{"id": f.id, "polygon": [list(p) for p in f.polygon.exterior.coords], "plane": list(f.plane),
                       "roof_type": f.roof_type, "pitch_rise": f.pitch_rise} for f in fs],
           "edges": [{"type": e.type, "p0": list(e.p0), "p1": list(e.p1), "facets": list(e.facets), "length_ft": e.length_ft}
                     for e in edges], "roof_outline": []}
    rec = edges_re.recompute(geom.load_roof(res), q)
    want: dict[str, float] = {}
    for e in rec.edges:
        want[e.type] = want.get(e.type, 0.0) + e.length_ft
    got = by_type(edges)
    for t in ("ridge", "hip", "valley", "flat_edge", "level_change", "transition"):
        assert abs(got.get(t, 0.0) - want.get(t, 0.0)) <= max(0.01 * want.get(t, 0.0), 0.5), (name, t)
    g_rim, w_rim = got.get("eave", 0.0) + got.get("rake", 0.0), want.get("eave", 0.0) + want.get("rake", 0.0)
    assert abs(g_rim - w_rim) <= max(0.01 * w_rim, 0.5)


def test_the_engine_result_carries_the_same_vocabulary():
    from engine_cases import run

    res = run("flat_pitched_step_d8")
    assert {e.type for e in res.edges} <= set(TYPES)
    assert [e.type for e in res.edges if e.type == "level_change"] and all(
        e.jump_ft is not None for e in res.edges if e.type == "level_change")
    shed = run("shed_d8")
    assert "ridge" not in {e.type for e in shed.edges} and sum(e.high_edge for e in shed.edges) == 1
    assert "level_change" in res.totals["lengths_ft"] and "step" not in res.totals["lengths_ft"]


# ----------------------------------------------------------------------------- the harness's measurement
def test_the_jump_measurement_is_the_harness_measurement():
    """engine.edge_measure.points_jump and tools.roof_eval.m_fit.edge_jump_m are one rule (0.2-1.5 m each side, a local
    linear fit evaluated on the line, None under 5 points a side): equal on random clouds, steps and gaps included."""
    from roof_measure.engine.edge_measure import points_jump
    from tools.roof_eval.m_fit import edge_jump_m

    rng = np.random.default_rng(7)
    for k in range(12):
        n = int(rng.integers(40, 900))
        xy = rng.uniform(-4, 4, (n, 2))
        z = 3 + 0.3 * xy[:, 0] + np.where(xy[:, 1] > 0, rng.uniform(0, 1.2), 0.0) + rng.normal(0, 0.02, n)
        q = np.c_[xy, z]
        p0, p1 = np.array([-3.0, 0.0]), np.array([3.0 + (k % 3), 0.2 * k])
        a, b = points_jump(q, p0, p1), edge_jump_m(q, (*p0, 0.0), (*p1, 0.0))
        assert (a is None) == (b is None) and (a is None or abs(a - b) < 1e-9)


def test_jump_points_follow_the_reference_rule():
    from roof_measure.engine.edge_measure import jump_points

    rng = np.random.default_rng(3)
    wall = Polygon([(0, 0), (10, 0), (10, 8), (0, 8)])
    ground = np.c_[rng.uniform(-6, 16, (300, 2)), np.zeros(300), np.full(300, 2.0)]
    roof = np.c_[rng.uniform(0, 10, (200, 1)), rng.uniform(0, 8, (200, 1)), np.full((200, 1), 4.0), np.ones((200, 1))]
    tree = np.c_[rng.uniform(0, 10, (50, 1)), rng.uniform(0, 8, (50, 1)), np.full((50, 1), 6.0), np.full((50, 1), 5.0)]
    low = np.c_[rng.uniform(0, 10, (50, 1)), rng.uniform(0, 8, (50, 1)), np.full((50, 1), 1.0), np.ones((50, 1))]
    far = np.c_[np.full((50, 1), 30.0), np.full((50, 1), 30.0), np.full((50, 1), 4.0), np.ones((50, 1))]
    out = jump_points(np.vstack([ground, roof, tree, low, far]), wall)
    assert len(out) == 200 and np.allclose(out[:, 2], 4.0)
    assert jump_points(None, wall) is None and jump_points(roof, wall) is None  # no ground: cannot tell height


# ----------------------------------------------------------------------------- dashed lines the roof does not show
def test_two_flat_facets_with_no_verified_jump_are_one_membrane_whatever_their_tilt():
    a = facet("a", [(0, 0), (6, 0), (6, 6), (0, 6)], (0, 0.02, 3.0))
    b = facet("b", [(6, 0), (12, 0), (12, 6), (6, 6)], (0.05, 0.0, 2.7))  # different planes, both under 2/12, no jump
    edges = build_edges([a, b], None, CTX)
    assert not [e for e in edges if len(e.facets) == 2]
    assert [m["facets"] for m in edge_diagnostics([a, b], DEFAULT)["mergeable"]] == [["a", "b"]]
    q = np.vstack([points_on(a), points_on(b, seed=1, offset=0.8)])  # a verified jump makes it a level change
    assert [e.type for e in build_edges([a, b], q, CTX) if len(e.facets) == 2] == ["level_change"]


def test_transition_needs_a_flat_facet_of_real_size():
    slope = facet("p", [(0, 4), (10, 4), (10, 9), (0, 9)], (0, 0.5, 1.0))  # z = 3 at y = 4
    big = facet("f", [(0, 0), (10, 0), (10, 4), (0, 4)], (0, 0, 3.0))  # 40 m2 of 90
    small = facet("s", [(0, 2.5), (10, 2.5), (10, 4), (0, 4)], (0, 0, 3.0))  # 15 m2 and 14% of the roof: real size
    tiny = facet("t", [(4, 3), (6, 3), (6, 4), (4, 4)], (0, 0, 3.0))  # 2 m2, touching the slope along 2 m
    assert [e.type for e in build_edges([big, slope], None, CTX) if len(e.facets) == 2] == ["transition"]
    assert [e.type for e in build_edges([small, slope], None, CTX) if len(e.facets) == 2] == ["transition"]
    assert "transition" not in {e.type for e in build_edges([tiny, slope], None, CTX)}
    diag = edge_diagnostics([tiny, slope], DEFAULT)
    assert diag["small_flat"] == [{"facets": ["t", "p"], "length_ft": pytest.approx(2 * M2FT, abs=0.2)}]


@pytest.mark.parametrize("length, jump, kept", [(0.8, 1.5, False), (1.5, 0.35, False), (1.9, 0.44, False), (1.5, 0.6, True),
                                                (3.0, 0.35, True), (3.0, 1.2, True)])
def test_a_level_change_stub_is_absorbed_and_reported(length, jump, kept):
    a = facet("a", [(0, 0), (6, 0), (6, length), (0, length)], (0, 0, 3.0))
    b = facet("b", [(6, 0), (12, 0), (12, length), (6, length)], (0, 0, 3.0 + jump))
    edges = build_edges([a, b], None, CTX, absorbed := [])
    lc = [e for e in edges if e.type == "level_change"]
    assert bool(lc) is kept and bool(absorbed) is (not kept)
    if absorbed:
        assert absorbed[0]["facets"] == ["a", "b"] and absorbed[0]["jump_ft"] == pytest.approx(jump / 0.3048, abs=0.1)
        assert edge_diagnostics([a, b], DEFAULT)["absorbed_level_changes"]
    assert {e.type for e in edges if len(e.facets) == 1} == {"flat_edge"}  # the outline is untouched
