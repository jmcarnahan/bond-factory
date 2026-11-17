"""The envelope partition on whole houses: two levels with a wall step, an L with valleys, a dormer.

Same synthetic method as test_planes_envelope.py (true facets by hand, shrunk and jittered clusters, production gap
fill as input, the roof turned and moved to an invented place).
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon
from test_planes_envelope import borders_of, local_plane, roof

from roof_measure.planes_envelope import envelope_detail


def _deg(line) -> float:
    (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
    return math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180.0


def test_two_level_house_one_straight_step_and_a_ridge_each():
    s = 0.5
    outline = [(0, 0), (30, 0), (30, 4), (50, 4), (50, 16), (30, 16), (30, 20), (0, 20)]
    facets = {"hs": ([(0, 0), (30, 0), (30, 10), (0, 10)], (0.0, s, 18.0)),  # high gable, eaves 18 ft
              "hn": ([(0, 10), (30, 10), (30, 20), (0, 20)], (0.0, -s, 28.0)),
              "ls": ([(30, 4), (50, 4), (50, 10), (30, 10)], (0.0, s, 7.0)),  # low gable, eaves 9 ft
              "ln": ([(30, 10), (50, 10), (50, 16), (30, 16)], (0.0, -s, 17.0))}
    res = envelope_detail(*roof(outline, facets))
    assert res.gate_failure is None
    assert sorted(sorted(sec["planes"]) for sec in res.sections) == [["hn", "hs"], ["ln", "ls"]]
    steps = borders_of(res, "step")
    assert steps and all(abs(x - 30.0) < 0.3 for st in steps for x, _ in st.coords)  # the shared wall, straight
    assert abs(sum(st.length for st in steps) - 12.0) < 0.5
    ridges = sorted(borders_of(res, "ridge"), key=lambda r: r.length)
    assert [round(r.length) for r in ridges] == [20, 30]
    assert all(abs(y - 10.0) < 0.05 for r in ridges for _, y in r.coords)
    assert abs(local_plane(res, "ls").area - 120.0) < 3.0


def test_l_house_valleys_are_straight_45_degree_lines():
    s, h0 = 0.5, 10.0
    outline = [(0, 0), (28, 0), (28, -20), (40, -20), (40, 20), (0, 20)]
    facets = {"n": ([(0, 10), (40, 10), (40, 20), (0, 20)], (0.0, -s, h0 + 20 * s)),
              "s": ([(0, 0), (28, 0), (34, 6), (40, 0), (40, 10), (0, 10)], (0.0, s, h0)),
              "w": ([(28, -20), (34, -20), (34, 6), (28, 0)], (s, 0.0, h0 - 28 * s)),
              "e": ([(34, -20), (40, -20), (40, 0), (34, 6)], (-s, 0.0, h0 + 40 * s))}
    res = envelope_detail(*roof(outline, facets))
    assert res.gate_failure is None, res.gate_failure
    valleys = borders_of(res, "valley")
    assert len(valleys) == 2
    for v in valleys:
        assert abs(v.length - 6.0 * math.sqrt(2)) < 0.4
        assert min(abs(_deg(v) - 45.0), abs(_deg(v) - 135.0)) < 0.5
    ridges = {round(r.length): r for r in borders_of(res, "ridge")}
    assert set(ridges) == {26, 40}
    assert all(abs(x - 34.0) < 0.05 for x, _ in ridges[26].coords)
    assert abs(local_plane(res, "w").area - 6 * 20 - 18) < 3.0  # 6 x 20 plus the triangle up to the valley meet


def test_dormer_plane_survives_inside_the_main_slope():
    s, h0 = 0.5, 10.0
    dormer = Polygon([(16, 2), (24, 2), (24, 9), (16, 9)])
    outline = [(0, 0), (40, 0), (40, 24), (0, 24)]
    facets = {"s": ([(0, 0), (40, 0), (40, 12), (0, 12)], (0.0, s, h0)),
              "n": ([(0, 12), (40, 12), (40, 24), (0, 24)], (0.0, -s, h0 + 24 * s)),
              "d": (list(dormer.exterior.coords)[:-1], (0.0, -2.0 / 12.0, h0 + 6.0))}  # a shed dormer above the slope
    res = envelope_detail(*roof(outline, facets, drop={"s": dormer.buffer(0.8)}))
    assert res.gate_failure is None, res.gate_failure
    assert "d" not in res.merged_small
    d = local_plane(res, "d")
    assert 30.0 < d.area < 70.0
    assert d.intersection(dormer).area > 0.8 * d.area
    assert local_plane(res, "n").area > 470.0  # the dormer never takes the other side of the ridge


def test_line_position_comes_from_where_the_clusters_touch():
    s, h0 = 0.25, 10.0  # 3/12: a 0.75 ft height error in one plane moves the computed ridge 1.5 ft
    outline = [(0, 0), (40, 0), (40, 24), (0, 24)]
    facets = {"s": ([(0, 0), (40, 0), (40, 12), (0, 12)], (0.0, s, h0)),
              "n": ([(0, 12), (40, 12), (40, 24), (0, 24)], (0.0, -s, h0 + 24 * s + 0.75))}  # the fit is 0.75 ft high
    res = envelope_detail(*roof(outline, facets))
    assert res.gate_failure is None
    (ridge,) = borders_of(res, "ridge")
    assert all(abs(y - 12.0) < 0.4 for _, y in ridge.coords)  # measured, not the computed 13.5
    rec = next(r for r in res.lines if r["kind"] == "meet")
    assert abs(rec["measured_shift_ft"]) > 1.0


def test_a_seam_never_offsets_the_ridge():
    s, h0 = 0.25, 10.0
    outline = [(0, 0), (40, 0), (40, 24), (0, 24)]
    facets = {"s": ([(0, 0), (40, 0), (40, 12), (0, 12)], (0.0, s, h0)),
              "n1": ([(0, 12), (25, 12), (25, 24), (0, 24)], (0.0, -s, h0 + 24 * s)),
              "n2": ([(25, 12), (40, 12), (40, 24), (25, 24)], (0.0, -0.2, h0 + 3.0 + 2.4 + 0.3))}  # flatter, 0.3 ft off
    res = envelope_detail(*roof(outline, facets))
    assert res.gate_failure is None
    ridges = borders_of(res, "ridge")
    ys = [y for r in ridges for _, y in r.coords]
    assert len(ridges) == 2 and max(ys) - min(ys) < 0.05  # one straight ridge across the n1/n2 seam
    assert [b["kind"] for b in res.borders if {b["a"], b["b"]} == {"n1", "n2"}] == ["seam"]


def test_a_flat_roof_and_a_slope_are_separate_sections_with_a_step():
    outline = [(0, 0), (40, 0), (40, 30), (0, 30)]
    facets = {"f": ([(0, 0), (40, 0), (40, 18), (0, 18)], (0.0, 0.0, 12.0)),  # flat at 12 ft
              "p": ([(0, 18), (40, 18), (40, 30), (0, 30)], (0.0, 0.25, 7.5))}  # a slope rising north from 12 ft
    res = envelope_detail(*roof(outline, facets))
    assert res.gate_failure is None
    assert len({p.section for p in res.planes}) == 2
    assert {b["kind"] for b in res.borders} == {"step"}


def bent_ranch(bend: float):
    """Two equal 6/12 gables (24 ft wide, 40 ft long) meeting at a mitre, the second wing turned by ``bend`` degrees:
    a hip on the convex side of the mitre, a valley on the concave side, both between planes facing ``bend`` apart."""
    s, h0 = 0.5, 10.0
    t = math.radians(bend)
    a, n = (math.cos(t), math.sin(t)), (-math.sin(t), math.cos(t))
    k = math.tan(t / 2)  # the mitre: x = -k y

    def at(u, v):
        return u * a[0] + v * n[0], u * a[1] + v * n[1]

    outline = [(-40, 0), (0, 0), at(40, 0), at(40, 24), (-24 * k, 24), (-40, 24)]
    facets = {"As": ([(-40, 0), (0, 0), (-12 * k, 12), (-40, 12)], (0.0, s, h0)),
              "An": ([(-40, 12), (-12 * k, 12), (-24 * k, 24), (-40, 24)], (0.0, -s, h0 + 24 * s)),
              "Bs": ([(0, 0), at(40, 0), at(40, 12), (-12 * k, 12)], (s * n[0], s * n[1], h0)),
              "Bn": ([(-12 * k, 12), at(40, 12), at(40, 24), (-24 * k, 24)], (-s * n[0], -s * n[1], h0 + 24 * s))}
    return roof(outline, facets)


def test_a_wing_bent_20_degrees_has_its_hip_and_valley():
    from roof_measure.planes_model import model_from_planes

    planes, raw, fp = bent_ranch(20.0)
    res = envelope_detail(planes, raw, fp)
    assert res.gate_failure is None
    kinds = {frozenset((b["a"], b["b"])): b["kind"] for b in res.borders}
    assert kinds[frozenset(("As", "Bs"))] == "hip" and kinds[frozenset(("An", "Bn"))] == "valley"
    m = model_from_planes(res.planes, fp, borders=res.borders)
    t = m["totals"]["lengths_ft"]
    mitre = math.hypot(12.0 / math.cos(math.radians(10.0)), 6.0)  # plan 12 / cos(bend / 2), rising 6 ft at 6/12
    assert t["hip"] == pytest.approx(mitre, abs=0.6) and t["valley"] == pytest.approx(mitre, abs=0.6)


def test_a_level_ridge_drawn_a_few_degrees_off_stays_a_ridge():
    planes, raw, fp = bent_ranch(40.0)  # the second wing's ridge is turned 5 degrees onto the 45-degree diagonal
    res = envelope_detail(planes, raw, fp)
    assert res.gate_failure is None
    ridge = sum(b["length_ft"] for b in res.borders if {b["a"], b["b"]} == {"Bs", "Bn"} and b["kind"] == "ridge")
    assert ridge > 30.0


def test_a_plane_outside_the_main_part_of_the_region_refuses_the_partition():
    from shapely.ops import unary_union

    planes, raw, fp = bent_ranch(20.0)
    shed = Polygon([(300, 300), (308, 300), (308, 308), (300, 308)])  # a detached carport roof far from the house
    p0 = planes[0]
    import dataclasses

    extra = dataclasses.replace(p0, id="G", polygon=[list(q) for q in list(shed.exterior.coords)[:-1]],
                                plan_area_sqft=shed.area)
    region = unary_union([fp, shed])
    res = envelope_detail([*planes, extra], {**raw, "G": shed.buffer(-0.5)}, region)
    assert res.gate_failure is not None and "outside" in res.gate_failure


def test_filled_pct_is_the_unseen_share_of_the_new_polygon():
    planes, raw, fp = bent_ranch(20.0)
    res = envelope_detail(planes, raw, fp)
    for p in res.planes:
        g = Polygon(p.polygon, p.holes)
        seen = raw[p.id].intersection(g).area
        assert p.filled_pct == pytest.approx(100.0 * (g.area - seen) / g.area, abs=0.1)
