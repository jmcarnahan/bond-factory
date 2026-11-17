"""Straight plane boundaries (planes_straight.straighten): wobbly clusters come back as a roof a roofer recognises.

Every shape is synthetic at an invented place in the model frame: planes are built from straight roof lines with a
deterministic wobble added to every shared border, the way LiDAR cell clusters leave them.
"""

from __future__ import annotations

import logging
import math

import pytest
from quality_helpers import block, blockset
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from roof_measure import planes_straight
from roof_measure.planes import Plane, snap_planes, snap_with_stats
from roof_measure.planes_straight import straighten


def wob(p: tuple[float, float], q: tuple[float, float], n: int = 9, amp: float = 0.35, phase: float = 0.0):
    """Points from p to q (both included) with a perpendicular wobble in between."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = math.hypot(dx, dy)
    nx, ny = -dy / length, dx / length
    pts = [p]
    for i in range(1, n):
        t = i / n
        off = amp * math.sin(7.3 * i + phase) * (1 if i % 2 else -1) * 0.8
        pts.append((p[0] + dx * t + nx * off, p[1] + dy * t + ny * off))
    pts.append(q)
    return pts


def chain(a, b, **kw):
    return wob(a, b, **kw)


def rev(pts):
    return list(reversed(pts))


def mk(pid: str, ring: list[tuple[float, float]], pitch: float, aspect: float | None) -> Plane:
    poly = Polygon(ring)
    if not poly.exterior.is_ccw:
        ring = list(reversed(ring))
        poly = Polygon(ring)
    flat = aspect is None
    area = round(poly.area, 1)
    return Plane(id=pid, polygon=[[round(x, 2), round(y, 2)] for x, y in ring], pitch_rise=0.0 if flat else pitch,
                 aspect_deg=aspect, plan_area_sqft=area,
                 surface_area_sqft=round(area / math.cos(math.atan((0.0 if flat else pitch) / 12)), 1), height_ft=10.0,
                 rms_ft=0.1, filled_pct=0.0)


def join(*parts):
    """One ring from chains that share end points."""
    out = []
    for part in parts:
        out.extend(part[:-1])
    return out


def drift_ok(before: list[Plane], after: list[Plane]) -> None:
    for b, a in zip(before, after, strict=True):
        assert abs(a.plan_area_sqft - b.plan_area_sqft) <= max(0.10 * b.plan_area_sqft, 3.0) + 0.2, (b.id, b.plan_area_sqft, a.plan_area_sqft)
    sb, sa = sum(p.surface_area_sqft for p in before), sum(p.surface_area_sqft for p in after)
    assert abs(sa - sb) <= 0.03 * sb


def shared_chain(a: Plane, b: Plane):
    """The part of the two outlines they share: a line or collection of lines (empty when they only touch)."""
    return a.shape().boundary.intersection(b.shape().boundary)


def no_gap_no_overlap(planes: list[Plane], outline: Polygon, tol: float = 0.01) -> None:
    shapes = [p.shape() for p in planes]
    assert all(s.is_valid for s in shapes)
    assert max((a.intersection(b).area for i, a in enumerate(shapes) for b in shapes[i + 1:]), default=0.0) <= 0.5
    assert outline.symmetric_difference(unary_union(shapes)).area <= tol * outline.area


def angle_of(line) -> float:
    (x1, y1), (x2, y2) = line.coords[0], line.coords[-1]
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def gable():
    ridge = chain((0, 12), (40, 12), n=15)
    south = mk("s", [(0, 0), (40, 0), (40, 12), *rev(ridge)[1:-1], (0, 12)], 6.0, 180.0)
    north = mk("n", [(0, 12), *ridge[1:-1], (40, 12), (40, 24), (0, 24)], 6.0, 0.0)
    return Polygon([(0, 0), (40, 0), (40, 24), (0, 24)]), [south, north]


def test_a_wobbly_gable_comes_back_as_two_rectangles_sharing_the_ridge():
    outline, planes = gable()
    assert all(len(p.polygon) > 15 for p in planes)
    out = straighten(planes, outline)
    assert [p.straightened for p in out] == [True, True]
    assert [len(p.polygon) for p in out] == [4, 4]
    ridge = shared_chain(*out)
    assert ridge.geom_type == "LineString" and ridge.length == pytest.approx(40.0, abs=0.6)
    assert min(angle_of(ridge), 180.0 - angle_of(ridge)) <= 0.5
    assert max(y for _, y in ridge.coords) - min(y for _, y in ridge.coords) <= 0.02  # one straight horizontal line
    no_gap_no_overlap(out, outline)
    drift_ok(planes, out)


def test_a_wobbly_four_plane_hip_has_the_45_degree_hips():
    # the straight shape: south and north are trapezoids, east and west triangles; the hips run at 45 degrees
    fp = Polygon([(0, 0), (40, 0), (40, 24), (0, 24)])
    a, b = (12, 12), (28, 12)
    sw, se = chain((0, 0), a, n=11, phase=0.3), chain((40, 0), b, n=11, phase=1.1)
    nw, ne = chain((0, 24), a, n=11, phase=2.0), chain((40, 24), b, n=11, phase=2.7)
    ridge = chain(a, b, n=9, phase=0.9)
    south = mk("s", [(0, 0), (40, 0), *se[1:], *rev(ridge)[1:], *rev(sw)[1:-1]], 4.0, 180.0)
    east = mk("e", [(40, 0), (40, 24), *ne[1:], *rev(se)[1:-1]], 4.0, 90.0)
    north = mk("n", [(40, 24), (0, 24), *nw[1:], *ridge[1:], *rev(ne)[1:-1]], 4.0, 0.0)
    west = mk("w", [(0, 24), (0, 0), *sw[1:], *rev(nw)[1:-1]], 4.0, 270.0)
    planes = [south, east, north, west]
    assert all(Polygon(p.polygon).is_valid for p in planes)
    out = straighten(planes, fp)
    assert all(p.straightened for p in out), "the hip did not straighten"
    by = {p.id: p for p in out}
    assert len(by["s"].polygon) <= 4 and len(by["n"].polygon) <= 4 and len(by["e"].polygon) <= 3 and len(by["w"].polygon) <= 3
    for pair in (("s", "w"), ("s", "e"), ("n", "w"), ("n", "e")):
        hipline = shared_chain(by[pair[0]], by[pair[1]])
        assert hipline.geom_type == "LineString", pair
        ang = angle_of(hipline)
        assert min(abs(ang - 45), abs(ang - 135)) <= 1.0, (pair, ang)
    no_gap_no_overlap(out, fp)
    drift_ok(planes, out)


def test_an_l_shaped_house_with_a_valley_keeps_the_valley_straight():
    outline = Polygon([(0, 0), (40, 0), (40, 20), (20, 20), (20, 40), (0, 40)])
    valley = chain((20, 20), (0, 0), n=13, amp=0.4)
    p1 = mk("a", [(0, 0), (40, 0), (40, 20), *valley[:-1]], 5.0, 180.0)
    p2 = mk("b", [(20, 20), (20, 40), (0, 40), (0, 0), *rev(valley)[1:-1]], 5.0, 270.0)
    out = straighten([p1, p2], outline)
    assert all(p.straightened for p in out)
    line = shared_chain(*out)
    assert line.geom_type == "LineString"
    assert min(abs(angle_of(line) - 45), abs(angle_of(line) - 135)) <= 1.0
    assert all(len(p.polygon) <= 5 for p in out)
    no_gap_no_overlap(out, outline)
    drift_ok([p1, p2], out)


def test_a_two_level_house_keeps_the_step_line_straight_and_both_levels():
    outline = Polygon([(0, 0), (50, 0), (50, 30), (0, 30)])
    step = chain((20, 0), (20, 30), n=12, amp=0.3)
    high = mk("hi", [(0, 0), *step, (0, 30)], 6.0, 180.0)
    low = mk("lo", [*step, (50, 30), (50, 0)], 3.0, 180.0)
    high.height_ft = 14.0
    low.height_ft = 9.0
    out = straighten([high, low], outline)
    assert [p.id for p in out] == ["hi", "lo"] and all(p.straightened for p in out)
    assert {p.height_ft for p in out} == {14.0, 9.0}
    line = shared_chain(*out)
    assert line.geom_type == "LineString"
    xs = [x for x, _ in line.coords]
    assert max(xs) - min(xs) <= 0.01  # the step is one vertical line
    assert [len(p.polygon) for p in out] == [4, 4]
    no_gap_no_overlap(out, outline)


def test_a_real_hole_stays_a_hole():
    outline = Polygon([(0, 0), (40, 0), (40, 30), (0, 30)])
    hole = Polygon([(15, 10), (25, 10), (25, 18), (15, 18)])
    # a ring of planes round a flat deck no LiDAR plane covers
    west = mk("w", [(0, 0), (15, 0), (15, 10), (15, 18), (15, 30), (0, 30)], 5.0, 270.0)
    east = mk("e", [(25, 0), (40, 0), (40, 30), (25, 30), (25, 18), (25, 10)], 5.0, 90.0)
    south = mk("s", [(15, 0), (25, 0), (25, 10), (15, 10)], 5.0, 180.0)
    north = mk("n", [(15, 18), (25, 18), (25, 30), (15, 30)], 5.0, 0.0)
    planes = [west, east, south, north]
    out = straighten(planes, outline)
    assert all(p.straightened for p in out)
    union = unary_union([p.shape() for p in out])
    assert not union.contains(Point(20, 14))  # still no plane over the deck
    assert union.area == pytest.approx(outline.area - hole.area, rel=0.01)
    assert outline.difference(union).area == pytest.approx(hole.area, rel=0.05)
    no_gap_no_overlap(out, outline.difference(hole))


def test_the_outline_is_never_moved():
    outline, planes = gable()
    out = straighten(planes, outline)
    ring = {(x, y) for p in out for x, y in p.polygon}
    for corner in outline.exterior.coords:
        assert (float(corner[0]), float(corner[1])) in ring
    for p in out:  # every outer side of a plane lies on the outline
        for (x1, y1), (x2, y2) in zip(p.polygon, p.polygon[1:] + p.polygon[:1], strict=True):
            mid = Point((x1 + x2) / 2, (y1 + y2) / 2)
            on_outline = outline.exterior.distance(mid) < 0.01
            on_ridge = abs(y1 - y2) < 0.01 and 11.0 < y1 < 13.0
            assert on_outline or on_ridge


def test_a_straightening_that_fails_its_checks_returns_the_planes_unchanged(monkeypatch, caplog):
    outline, planes = gable()
    monkeypatch.setattr(planes_straight, "_attempt", lambda *a, **k: ([], "plane s area drift +99.0 sq ft"))
    monkeypatch.setattr(planes_straight, "_attempt_geometric", lambda *a, **k: ([], "plane s area drift +99.0 sq ft"))
    with caplog.at_level(logging.INFO, logger="roof_measure.planes"):
        out = straighten(planes, outline)
    assert all(not p.straightened for p in out)
    assert [p.polygon for p in out] == [p.polygon for p in planes]
    assert [p.plan_area_sqft for p in out] == [p.plan_area_sqft for p in planes]
    assert [p.raw_plan_area_sqft for p in out] == [p.plan_area_sqft for p in planes]  # set even when nothing changed
    assert any("not straightened" in r.message for r in caplog.records)


def test_an_invalid_input_plane_is_returned_unchanged():
    bow = mk("bow", [(0, 0), (10, 10), (10, 0), (0, 10)], 4.0, 180.0)
    bow.polygon = [[0, 0], [10, 10], [10, 0], [0, 10]]
    ok = mk("ok", [(10, 0), (20, 0), (20, 10), (10, 10)], 4.0, 0.0)
    out = straighten([bow, ok], Polygon([(0, 0), (20, 0), (20, 10), (0, 10)]))
    assert not any(p.straightened for p in out)


def test_the_area_bounds_reject_a_result_that_moves_too_much():
    outline, planes = gable()
    moved = [Polygon(p.polygon).buffer(-1.0, join_style=2) for p in planes]  # each plane shrinks by about 10%+
    why = planes_straight._passes(planes, [p.shape() for p in planes], moved, outline, outline)
    assert why is not None and ("drift" in why or "covered" in why or "overlap" in why)


def test_straightening_never_changes_the_numbers_a_plane_keeps():
    outline, planes = gable()
    out = straighten(planes, outline)
    for b, a in zip(planes, out, strict=True):
        assert (a.id, a.pitch_rise, a.aspect_deg, a.height_ft, a.rms_ft) == (b.id, b.pitch_rise, b.aspect_deg, b.height_ft, b.rms_ft)
        assert a.surface_area_sqft == pytest.approx(a.plan_area_sqft / math.cos(math.atan(a.pitch_rise / 12)), abs=0.1)
        assert a.plan_area_sqft == pytest.approx(a.shape().area, abs=0.1)


def test_snapping_straightens_by_default_and_the_flag_turns_it_off():
    sq = [(0, 0), (40, 0), (40, 24), (0, 24)]
    ridge = chain((0, 12), (40, 12), n=15, amp=0.5)
    south = block("south", [(0, 0), (40, 0), (40, 12), *rev(ridge)[1:-1], (0, 12)], aspect=180.0)
    north = block("north", [(0, 12), *ridge[1:-1], (40, 12), (40, 24), (0, 24)], aspect=0.0)
    bs = blockset(sq, [south, north])
    on = snap_planes(bs, clip_to_footprint=True)
    off = snap_planes(bs, clip_to_footprint=True, straighten=False)
    assert all(p.straightened for p in on) and not any(p.straightened for p in off)
    assert sum(len(p.polygon) for p in on) < sum(len(p.polygon) for p in off)
    assert [p.to_dict()["straightened"] for p in on] == [True, True]
    assert all(d["raw_plan_area_sqft"] > 0 for d in (p.to_dict() for p in on))
    res = snap_with_stats(bs, clip_to_footprint=True)
    assert not res.failed and res.footprint_area_sqft == pytest.approx(960.0, abs=1)
    no_gap_no_overlap(on, Polygon(sq))


@pytest.mark.parametrize("name", ["site1", "two_level", "handmade", "hip", "simple_gable", "simple_hip", "plain_gable"])
def test_every_committed_blocks_fixture_straightens_within_the_bounds(name, monkeypatch):
    monkeypatch.setattr("roof_measure.planes_envelope.envelope_planes", lambda *a, **k: None)  # this tests the in-place method
    from quality_helpers import HERE, SITE1, SITE1_HANDMADE, TWO_LEVEL, hip_rectangle, invariant_problems

    from roof_measure.classify import BlockSet

    paths = {"site1": SITE1, "two_level": TWO_LEVEL, "handmade": SITE1_HANDMADE,
             **{k: HERE / "fixtures" / f"{k}_house_blocks.json" for k in ("simple_gable", "simple_hip", "plain_gable")}}
    bs = hip_rectangle() if name == "hip" else BlockSet.load(paths[name])
    off = snap_with_stats(bs, clip_to_footprint=True, straighten=False).planes
    on = snap_with_stats(bs, clip_to_footprint=True).planes
    assert [p.id for p in on] == [p.id for p in off]
    assert all(p.straightened for p in on), "a committed fixture fell back to the unstraightened planes"
    assert invariant_problems(bs, on) == []
    drift_ok(off, on)
    assert sum(len(p.polygon) for p in on) <= sum(len(p.polygon) for p in off)  # never more vertices
    for p in on:
        assert p.raw_plan_area_sqft is not None and p.raw_plan_area_sqft > 0


def test_a_plane_carries_its_fitted_equation_and_the_height_is_the_cluster_mean_at_its_centroid():
    sq = [(0, 0), (40, 0), (40, 24), (0, 24)]
    south = block("south", [(0, 0), (40, 0), (40, 12), (0, 12)], pitch=6.0, aspect=180.0, z=13.0)
    north = block("north", [(0, 12), (40, 12), (40, 24), (0, 24)], pitch=6.0, aspect=0.0, z=13.0)
    planes = {p.id: p for p in snap_planes(blockset(sq, [south, north]), clip_to_footprint=True)}
    a, b, c = planes["south"].plane_eq  # faces south: the height rises towards the north
    assert (a, b) == (pytest.approx(0.0, abs=1e-6), pytest.approx(0.5))
    assert a * 20 + b * 6 + c == pytest.approx(south["height_above_ground_ft"], abs=0.01)  # at the cluster centroid
    _, b2, c2 = planes["north"].plane_eq
    assert b2 == pytest.approx(-0.5)
    assert planes["south"].to_dict()["plane_eq"] == [a, b, c]
    # the two planes meet (equal height) along the ridge y = 12 of the gable
    assert (b - b2) * 12 + (c - c2) == pytest.approx(0.0, abs=0.1)


def test_borders_are_listed_with_their_kind_and_the_planes_share_their_points_exactly():
    outline, planes = gable()
    for p in planes:
        p.plane_eq = [0.0, 0.5 if p.id == "s" else -0.5, 6.0 if p.id == "s" else 18.0]  # heights agree at y = 12
    out, borders = planes_straight.straighten_with_borders(planes, outline)
    assert len(borders) == 1
    b = borders[0]
    assert {b["a"], b["b"]} == {"s", "n"} and b["kind"] == "intersection" and abs(b["step_ft"]) <= 0.1
    assert b["length_ft"] == pytest.approx(40.0, abs=0.6) and len(b["segment"]) == 2
    s, n = out
    assert set(map(tuple, b["segment"])) <= set(map(tuple, s.polygon)) & set(map(tuple, n.polygon))


def test_a_height_step_is_listed_as_a_step_with_the_higher_plane():
    outline = Polygon([(0, 0), (50, 0), (50, 30), (0, 30)])
    step = chain((20, 0), (20, 30), n=12, amp=0.3)
    high = mk("hi", [(0, 0), *step, (0, 30)], 6.0, 180.0)
    low = mk("lo", [*step, (50, 30), (50, 0)], 3.0, 180.0)
    high.plane_eq, low.plane_eq = [0.0, -0.5, 25.0], [0.0, -0.25, 12.0]  # 10 ft apart at y = 0, 4 ft at y = 30
    _, borders = planes_straight.straighten_with_borders([high, low], outline)
    assert len(borders) == 1 and borders[0]["kind"] == "step" and borders[0]["high"] == "hi"
    assert borders[0]["step_ft"] == pytest.approx(7.0, abs=0.1) or borders[0]["step_ft"] > 3.0


def test_a_rotated_roof_gets_its_ridge_parallel_to_the_building_axis():
    import math as m
    ang = m.radians(30.0)
    rot = lambda x, y: (x * m.cos(ang) - y * m.sin(ang) + 100.0, x * m.sin(ang) + y * m.cos(ang) + 50.0)
    ridge = [rot(x, y) for x, y in chain((0, 12), (40, 12), n=15, amp=0.5)]
    south = mk("s", [rot(0, 0), rot(40, 0), rot(40, 12), *rev(ridge)[1:-1], rot(0, 12)], 6.0, (180.0 + 30.0) % 360)
    north = mk("n", [rot(0, 12), *ridge[1:-1], rot(40, 12), rot(40, 24), rot(0, 24)], 6.0, 30.0)
    outline = Polygon([rot(0, 0), rot(40, 0), rot(40, 24), rot(0, 24)])
    out = straighten([south, north], outline)
    line = shared_chain(*out)
    assert line.geom_type == "LineString" and abs(angle_of(line) - 30.0) <= 0.5
    assert [len(p.polygon) for p in out] == [4, 4]


def test_planes_are_on_one_height_datum_when_the_blocks_local_grounds_differ():
    sq = [(0, 0), (40, 0), (40, 24), (0, 24)]
    south = block("south", [(0, 0), (40, 0), (40, 12), (0, 12)], pitch=6.0, aspect=180.0, z=13.0)
    north = block("north", [(0, 12), (40, 12), (40, 24), (0, 24)], pitch=6.0, aspect=0.0, z=13.0)
    south["height_above_ground_ft"] = 13.0 - 0.0  # local ground 0.0 ft
    north["height_above_ground_ft"] = 13.0 - 2.6  # local ground 2.6 ft: the same absolute roof, a different "ground"
    res = snap_with_stats(blockset(sq, [south, north]), clip_to_footprint=True)
    s, n = {p.id: p for p in res.planes}["south"], {p.id: p for p in res.planes}["north"]
    assert s.height_ft == 13.0 and n.height_ft == 10.4  # the output key keeps its meaning
    (_, b1, c1), (_, b2, c2) = s.plane_eq, n.plane_eq
    assert (b1 - b2) * 12 + (c1 - c2) == pytest.approx(0.0, abs=0.1)  # equal heights exactly on the ridge y = 12
    (border,) = res.borders
    assert border["kind"] in ("intersection", "ridge") and abs(border["step_ft"]) <= 0.1  # (planes_envelope names it ridge)
    ridge_y = {y for _, y in border["segment"]}
    assert all(abs(y - 12.0) <= 0.3 for y in ridge_y)
