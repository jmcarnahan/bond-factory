"""The envelope partition (planes_envelope): borders from plane equations, not from where LiDAR clusters stop.

Every roof is synthetic and closed-form: true facets and plane equations are written by hand in a local frame, then
rotated and moved to an invented place. The raw clusters are the true facets shrunk by 0.8 ft and jittered (10-30%
of the roof uncovered, as LiDAR leaves it) and the input tiling is the production gap fill of those clusters, so the
input borders are arbitrary the same way they are on real roofs.
"""

from __future__ import annotations

import math
import random

from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient

from roof_measure.planes import Plane
from roof_measure.planes_envelope import envelope_detail, envelope_planes
from roof_measure.planes_envelope_gate import expected_areas, gate
from roof_measure.planes_gaps import _fill_gaps

ANGLE = 17.0  # the whole roof is turned by this and moved to ORIGIN (invented)
ORIGIN = (431.7, -268.3)


def to_world(g):
    return affinity.translate(affinity.rotate(g, ANGLE, origin=(0, 0)), *ORIGIN)


def to_local(g):
    return affinity.rotate(affinity.translate(g, -ORIGIN[0], -ORIGIN[1]), -ANGLE, origin=(0, 0))


def eq_world(a: float, b: float, c: float) -> list[float]:
    """The local equation z = a x + b y + c in world coordinates."""
    r = math.radians(ANGLE)
    ga, gb = a * math.cos(r) - b * math.sin(r), a * math.sin(r) + b * math.cos(r)
    return [ga, gb, c - ga * ORIGIN[0] - gb * ORIGIN[1]]


def jitter(poly: Polygon, seed: int, amp: float = 0.3) -> Polygon:
    """The polygon with its outline wobbled by up to ``amp`` ft (deterministic)."""
    rnd = random.Random(seed)
    ring = LineString(poly.exterior.coords)
    n = max(8, int(ring.length))
    pts = []
    for k in range(n):
        p = ring.interpolate(k / n, normalized=True)
        q = ring.interpolate((k + 0.5) / n, normalized=True)
        dx, dy = q.x - p.x, q.y - p.y
        ln = math.hypot(dx, dy) or 1.0
        off = rnd.uniform(-amp, amp)
        pts.append((p.x - dy / ln * off, p.y + dx / ln * off))
    g = Polygon(pts)
    g = g if g.is_valid else g.buffer(0)
    for hole in poly.interiors:  # holes (a dormer cut out of a slope) stay holes
        g = g.difference(Polygon(hole))
    return g


def roof(outline: list[tuple[float, float]], facets: dict[str, tuple[list[tuple[float, float]], tuple[float, float, float]]],
         shrink: float = 0.8, drop: dict[str, Polygon] | None = None):
    """(planes, raw by id, world outline) for a roof given in local feet: facet rings and local equations."""
    fp = orient(to_world(Polygon(outline)), 1.0)
    ids, raws, eqs = [], [], []
    for n, (pid, (ring, eq)) in enumerate(facets.items()):
        g = Polygon(ring).buffer(-shrink, join_style=2)
        if drop and pid in drop:
            g = g.difference(drop[pid])
        g = max(getattr(g, "geoms", [g]), key=lambda q: q.area)
        ids.append(pid)
        raws.append(to_world(jitter(g, seed=n + 1)).intersection(fp))
        eqs.append(eq_world(*eq))
    tiled = _fill_gaps([r if r.area > 0 else None for r in raws], fp)
    planes = []
    for pid, r, t, e in zip(ids, raws, tiled, eqs, strict=True):
        t = orient(t, 1.0)
        s = math.hypot(e[0], e[1])
        aspect = None if s < 1e-9 else math.degrees(math.atan2(-e[0], -e[1])) % 360.0
        c = r.centroid
        planes.append(Plane(id=pid, polygon=[[x, y] for x, y in list(t.exterior.coords)[:-1]],
                            holes=[[[x, y] for x, y in list(h.coords)[:-1]] for h in t.interiors], pitch_rise=round(12 * s, 3),
                            aspect_deg=aspect, plan_area_sqft=t.area, surface_area_sqft=t.area * math.hypot(1, s),
                            height_ft=e[0] * c.x + e[1] * c.y + e[2], rms_ft=0.1, filled_pct=0.0,
                            raw_plan_area_sqft=r.area, plane_eq=e))
    return planes, dict(zip(ids, raws, strict=True)), fp


def borders_of(res, kind: str) -> list[LineString]:
    return [to_local(LineString(b["segment"])) for b in res.borders if b["kind"] == kind]


def local_plane(res, pid: str) -> Polygon:
    p = next(p for p in res.planes if p.id == pid)
    return to_local(Polygon(p.polygon, p.holes))


def gable(w: float = 24.0, ln: float = 40.0, p1: float = 6.0, p2: float = 6.0, h0: float = 10.0):
    """A gable along x: south plane pitch p1, north plane pitch p2, eaves at h0; the ridge where they meet."""
    s1, s2 = p1 / 12.0, p2 / 12.0
    yr = s2 * w / (s1 + s2)  # h0 + s1 y = h0 + s2 (w - y)
    out = [(0, 0), (ln, 0), (ln, w), (0, w)]
    return out, yr, {"s": ([(0, 0), (ln, 0), (ln, yr), (0, yr)], (0.0, s1, h0)),
                     "n": ([(0, yr), (ln, yr), (ln, w), (0, w)], (0.0, -s2, h0 + s2 * w))}


def test_symmetric_gable_ridge_on_the_middle_line():
    outline, yr, facets = gable()
    res = envelope_detail(*roof(outline, facets))
    assert res.gate_failure is None
    assert [s["method"] for s in res.sections] == ["envelope"]
    ridges = borders_of(res, "ridge")
    assert len(ridges) == 1 and abs(ridges[0].length - 40.0) < 0.2
    assert all(abs(y - yr) < 0.05 for _, y in ridges[0].coords)
    assert abs(local_plane(res, "s").area - local_plane(res, "n").area) < 1.0


def test_off_centre_gable_ridge_exactly_where_the_planes_meet():
    outline, yr, facets = gable(p1=4.0, p2=6.0)  # the steeper north side is the narrower one: yr = 14.4
    assert abs(yr - 14.4) < 1e-9
    planes, raw, fp = roof(outline, facets)
    res = envelope_detail(planes, raw, fp)
    assert res.gate_failure is None
    (ridge,) = borders_of(res, "ridge")
    assert all(abs(y - yr) < 0.05 for _, y in ridge.coords)
    assert abs(local_plane(res, "s").area - 40.0 * yr) < 1.0
    assert all(p.straighten_method == "envelope" and p.section == 0 for p in res.planes)


def test_hip_ridge_and_four_45_degree_hips():
    s, h0 = 0.5, 10.0
    outline = [(0, 0), (40, 0), (40, 24), (0, 24)]
    facets = {"s": ([(0, 0), (40, 0), (28, 12), (12, 12)], (0.0, s, h0)),
              "e": ([(40, 0), (40, 24), (28, 12)], (-s, 0.0, h0 + 40 * s)),
              "n": ([(40, 24), (0, 24), (12, 12), (28, 12)], (0.0, -s, h0 + 24 * s)),
              "w": ([(0, 24), (0, 0), (12, 12)], (s, 0.0, h0))}
    res = envelope_detail(*roof(outline, facets))
    assert res.gate_failure is None
    (ridge,) = borders_of(res, "ridge")
    assert abs(ridge.length - 16.0) < 0.3 and all(abs(y - 12.0) < 0.05 for _, y in ridge.coords)
    hips = borders_of(res, "hip")
    assert len(hips) == 4
    for h in hips:
        (x0, y0), (x1, y1) = h.coords[0], h.coords[-1]
        assert abs(h.length - 12.0 * math.sqrt(2)) < 0.3
        assert abs(abs(math.degrees(math.atan2(y1 - y0, x1 - x0))) % 90.0 - 45.0) < 0.5
    assert abs(local_plane(res, "e").area - 144.0) < 2.0 and abs(local_plane(res, "s").area - 336.0) < 2.0


def test_facing_set_square_and_height_kept():
    outline, _, facets = gable()
    planes, raw, fp = roof(outline, facets)
    tilted = planes[0]
    a, b, c = tilted.plane_eq
    t = math.radians(6.0)  # turn the south plane's facing 6 degrees off the axis (a fit error)
    na, nb = a * math.cos(t) - b * math.sin(t), a * math.sin(t) + b * math.cos(t)
    cen = raw[tilted.id].centroid
    tilted.plane_eq = [na, nb, a * cen.x + b * cen.y + c - na * cen.x - nb * cen.y]
    res = envelope_detail(planes, raw, fp)
    assert res.gate_failure is None
    assert abs(res.moves["s"]["turn_deg"] - 6.0) < 0.05
    out = next(p for p in res.planes if p.id == "s")
    assert abs(out.plane_eq[0] - a) < 1e-4 and abs(out.plane_eq[1] - b) < 1e-4  # back on the axis
    assert abs(out.plane_eq[0] * cen.x + out.plane_eq[1] * cen.y + out.plane_eq[2] - tilted.height_ft) < 0.01


def test_output_is_a_tiling_with_shared_vertices():
    outline, _, facets = gable(p1=4.0, p2=6.0)
    planes, raw, fp = roof(outline, facets)
    got = envelope_planes(planes, raw, fp)
    assert got is not None
    out, borders = got
    shapes = [Polygon(p.polygon, p.holes) for p in out]
    assert abs(sum(g.area for g in shapes) - fp.area) < 0.01 * fp.area
    assert shapes[0].intersection(shapes[1]).area < 1e-6
    shared = {tuple(q) for q in out[0].polygon} & {tuple(q) for q in out[1].polygon}
    assert len(shared) == 2  # the ridge's two ends, identical on both planes
    assert {b["kind"] for b in borders} == {"ridge"}
    for p in out:
        assert abs(p.surface_area_sqft - p.plan_area_sqft / math.cos(math.atan(p.pitch_rise / 12.0))) < 0.2


def test_expected_area_is_raw_plus_the_nearest_bare_roof():
    fp = Polygon([(0, 0), (20, 0), (20, 10), (0, 10)])
    left, right = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)]), Polygon([(16, 0), (20, 0), (20, 10), (16, 10)])
    got = expected_areas(["a", "b"], [left, right], fp)
    assert abs(got["a"] - 110.0) < 3.0 and abs(got["b"] - 90.0) < 3.0  # the bare 10 ft splits at x = 11


def test_gate_refuses_a_lost_plane_and_a_changed_total():
    outline, _, facets = gable()
    planes, raw, fp = roof(outline, facets)
    res = envelope_detail(planes, raw, fp)
    raws = [raw[p.id] for p in planes]
    assert gate(planes, res.planes, raws, fp, []) is None
    assert "vanished" in gate(planes, res.planes[:1], raws, fp, ["n"])
    assert "plan area" in gate(planes, res.planes[:1], raws, fp, [])


def test_never_raises_and_returns_none_on_nonsense():
    assert envelope_planes([], {}, Polygon()) is None
    outline, _, facets = gable()
    planes, raw, fp = roof(outline, facets)
    planes[0].plane_eq = [float("nan"), 0.0, 1.0]
    assert envelope_planes(planes, raw, fp) is None
