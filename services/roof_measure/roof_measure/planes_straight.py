"""Straight plane boundaries: the snapped planes redrawn with few vertices and straight shared sides (internal).

``straighten(planes, footprint)`` takes the snapped planes (disjoint, tiling the roof outline) and returns the same
planes with simpler outlines: every border two planes share becomes ONE shared polyline with few vertices (both planes
get the identical points, so there is still no gap and no overlap), borders that run within a few degrees of a
dominant direction (the outline's main axis, its perpendicular and the two 45-degree hip directions, or the
intersection line of the two fitted planes) are turned onto it, collinear vertices go, and the outer edges stay on
the outline (the outline is never simplified or moved). Part of the outline no plane covers stays uncovered.

It is pure geometry (shapely only), deterministic and NEVER makes a roof worse: when no simplification tolerance gives a
result that passes its own checks (valid simple polygons, no overlap, coverage of the outline kept, every plane's plan
area within ``MAX_PLANE_DRIFT`` of the input, total surface area within ``MAX_TOTAL_DRIFT``) the input planes come back
unchanged with ``straightened`` False. Everything is on the planes' own feet frame; nothing here knows about LiDAR.
"""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import Any

from shapely.errors import ShapelyError
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import snap, unary_union

from .classify import polygons_of
from .planes_lines import geometric, plane_eq, z_at
from .planes_net import (
    MAX_PLANE_DRIFT,
    MIN_ANGLE_DEG,
    MIN_DRIFT_SQFT,
    _drop_collinear,
    _Net,
    _rings,
    _simplify_chains,
    _turn,
)

log = logging.getLogger("roof_measure.planes")


MAX_TOTAL_DRIFT = 0.03  # total surface area


MAX_OVERLAP_SQFT = 0.5


COVERAGE_LOSS = 0.005  # share of the tiled area the result may lose or gain


MIN_PLANE_SQFT = 4.0


def _axis_deg(outline: BaseGeometry) -> float:
    """Direction (degrees, 0-180) of the long side of the outline's minimum rotated rectangle."""
    parts = polygons_of(outline)
    if not parts:
        return 0.0
    rect = max(parts, key=lambda p: p.area).minimum_rotated_rectangle
    pts = list(rect.exterior.coords)
    if len(pts) < 5:
        return 0.0
    a, b, c = pts[0], pts[1], pts[2]
    e = (b[0] - a[0], b[1] - a[1]) if math.dist(a, b) >= math.dist(b, c) else (c[0] - b[0], c[1] - b[1])
    return math.degrees(math.atan2(e[1], e[0])) % 180.0


def _gradient(plane: Any) -> tuple[float, float] | None:
    """Plan gradient (rise per foot, x east y north) of a sloped plane; None for a flat one."""
    if plane.aspect_deg is None or not plane.pitch_rise:
        return None
    s = float(plane.pitch_rise) / 12.0
    a = math.radians(float(plane.aspect_deg))  # downslope compass bearing: the height rises the other way
    return -s * math.sin(a), -s * math.cos(a)


def _node_to(polys: list[Polygon]) -> list[Polygon]:
    """Insert into every polygon the vertices other polygons have on its sides (T-junctions), so edges match."""
    pts = MultiPoint([c for p in polys for ring in _rings(p) for c in ring])
    out = []
    for p in polys:
        q = snap(p, pts, 1.2 * GRID_FT)
        out.append(q if q.is_valid else p)
    return out


def _surface(area: float, pitch: float) -> float:
    return area / math.cos(math.atan(pitch / 12.0))


def _ring2(r: Any) -> list[list[float]]:
    return [[round(float(x), 2) + 0.0, round(float(y), 2) + 0.0] for x, y in list(r.coords)[:-1]]


def _build(planes: list[Any], polys: list[Polygon]) -> list[Any]:
    """The planes with the new outlines on the 0.01 ft grid; the areas are those of the rounded rings."""
    out = []
    for pl, g in zip(planes, polys, strict=True):
        g = orient(g, 1.0)
        shell, holes = _ring2(g.exterior), [_ring2(h) for h in g.interiors]
        area = float(Polygon(shell, holes).area)
        out.append(replace(pl, polygon=shell, holes=holes, plan_area_sqft=round(area, 1),
                           surface_area_sqft=round(_surface(area, float(pl.pitch_rise)), 1), straightened=True))
    return out


MIN_EDGE_FT = 0.5  # a side shorter than this, away from the outline, is a stub


def _on(boundary: BaseGeometry, a: tuple[float, float], b: tuple[float, float]) -> bool:
    """True when the side a-b lies along ``boundary``."""
    return bool(boundary.distance(Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) < 1e-3)


def _bad_vertex(polys: list[Polygon], outline: BaseGeometry) -> str | None:
    """A spike tip (an outline corner the input already had is not the straightening's doing) or a stub."""
    ob = outline.boundary
    for g in polys:
        for ring in _rings(g):
            n = len(ring)
            for i in range(n):
                a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
                v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
                n1, n2 = math.hypot(*v1), math.hypot(*v2)
                if n1 == 0 or n2 == 0:
                    return "a repeated vertex"
                ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))
                if ang < MIN_ANGLE_DEG and not (_on(ob, a, b) and _on(ob, b, c)):  # (an outline corner is not ours to fix)
                    return f"a spike of {ang:.1f} degrees"
                if n2 < MIN_EDGE_FT and not (ob.distance(Point(b)) < MIN_EDGE_FT and ob.distance(Point(c)) < MIN_EDGE_FT):
                    return "a side under half a foot"
    return None


def _passes(planes: list[Any], before: list[Polygon], after: list[Polygon], tiled: BaseGeometry,
            outline: BaseGeometry) -> str | None:
    """None when the result is acceptable, else why not."""
    if any(g.is_empty or not isinstance(g, Polygon) or not g.is_valid or g.area < MIN_PLANE_SQFT for g in after):
        return "a plane is empty, invalid or vanished"
    for pl, b, a in zip(planes, before, after, strict=True):
        if abs(a.area - b.area) > max(MAX_PLANE_DRIFT * b.area, MIN_DRIFT_SQFT):
            return f"plane {pl.id} area drift {a.area - b.area:+.1f} sq ft"
    tb = sum(_surface(b.area, float(pl.pitch_rise)) for pl, b in zip(planes, before, strict=True))
    ta = sum(_surface(a.area, float(pl.pitch_rise)) for pl, a in zip(planes, after, strict=True))
    if tb > 0 and abs(ta - tb) > MAX_TOTAL_DRIFT * tb:
        return f"total surface drift {100 * (ta - tb) / tb:+.1f}%"
    worst = max((a.intersection(b).area for i, a in enumerate(after) for b in after[i + 1:]), default=0.0)
    if worst > MAX_OVERLAP_SQFT:
        return f"overlap {worst:.2f} sq ft"
    bad = _bad_vertex(after, outline)
    if bad:
        return bad
    union = unary_union(after)
    if abs(union.area - tiled.area) > COVERAGE_LOSS * tiled.area or tiled.symmetric_difference(union).area > 2 * COVERAGE_LOSS * tiled.area:
        return "the covered area changed"
    return None


GRID_FT = 0.05
VOID_SQFT = 0.3  # an uncovered piece smaller than this is a seam between planes, not a hole
BUDGET_SCALES = (1.0, 0.85, 0.7, 0.55, 0.4, 0.25)  # share of each plane's allowed area drift spent on simplifying (the rest is a reserve)


def _attempt(planes: list[Any], before: list[Polygon], voids: list[Polygon], tiled: BaseGeometry, scale: float,
             dirs: list[float], turn: bool = True) -> tuple[list[Polygon], str | None]:
    faces = _node_to([*before, *voids])
    outer = unary_union(faces)  # the outline: planes and uncovered parts together
    net = _Net(faces, outer)
    net.drop(_simplify_chains(net, len(planes), scale))
    borders: dict[tuple[int, int], set[int]] = {}
    for n, rr in enumerate(net.rings[:len(planes)]):
        for ids in rr:
            for i, a in enumerate(ids):
                b = ids[(i + 1) % len(ids)]
                borders.setdefault((min(a, b), max(a, b)), set()).add(n)
    grads = {n: _gradient(pl) for n, pl in enumerate(planes)}
    if turn:
        _turn(net, borders, dirs, grads)
    _drop_collinear(net)
    after = _published(net.polygons()[:len(planes)])
    if not all(g.is_valid for g in after):
        return [], "turning the borders made a plane invalid"
    return after, _passes(planes, before, after, tiled, outer)


def _valid_grid(g: BaseGeometry) -> BaseGeometry:
    """The polygon on a 0.05 ft grid (so vertices two planes share coincide exactly); itself when that breaks it."""
    from shapely import set_precision

    q = set_precision(g, GRID_FT)
    return q if q.geom_type == "Polygon" and q.is_valid and not q.is_empty else g


def _share_vertices(polys: list[Polygon]) -> list[Polygon]:
    """Give every plane the vertices other planes have on its sides, so a shared border has the same points on both."""
    pts = [c for g in polys for r in _rings(g) for c in r]
    out = []
    for g in polys:
        rings = []
        for ring in _rings(g):
            new: list[tuple[float, float]] = []
            n = len(ring)
            for i in range(n):
                a, b = ring[i], ring[(i + 1) % n]
                new.append(a)
                ln = math.dist(a, b)
                if ln < 1e-9:
                    continue
                ins = []
                for q in pts:
                    if math.dist(q, a) < 1e-6 or math.dist(q, b) < 1e-6:
                        continue
                    t = ((q[0] - a[0]) * (b[0] - a[0]) + (q[1] - a[1]) * (b[1] - a[1])) / (ln * ln)
                    if 0.0 < t < 1.0 and math.hypot(q[0] - (a[0] + t * (b[0] - a[0])), q[1] - (a[1] + t * (b[1] - a[1]))) < 0.02:
                        ins.append((t, q))
                new += [q for _, q in sorted(ins)]
            rings.append(new)
        out.append(Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3]))
    return out


def _published(polys: list[Polygon]) -> list[Polygon]:
    """The polygons as they will be published: counter-clockwise, on the 0.01 ft grid, sharing their border vertices."""
    rounded = [Polygon(_ring2(orient(g, 1.0).exterior), [_ring2(h) for h in orient(g, 1.0).interiors])
               if g.is_valid and not g.is_empty else g for g in polys]
    if not all(g.is_valid for g in rounded):
        return rounded
    shared = _share_vertices(rounded)
    return shared if all(g.is_valid for g in shared) else rounded


def _attempt_geometric(planes: list[Any], before: list[Polygon], voids: list[Polygon], tiled: BaseGeometry, scale: float,
                       dirs: list[float], axis: float) -> tuple[list[Polygon], str | None]:
    """Every border between two planes becomes one straight roof line (ridge/hip/valley or a straight step)."""
    faces = _node_to([*before, *voids])
    outer = unary_union(faces)
    net = _Net(faces, outer)
    why = geometric(net, planes, dirs, axis, scale)
    if why:
        return [], why
    net.drop(_simplify_chains(net, len(planes), scale))  # borders that fit no line keep the budgeted simplification
    _drop_collinear(net)
    after = _published(net.polygons()[:len(planes)])
    if not all(g.is_valid for g in after):
        return [], "moving the borders made a plane invalid"
    return after, _passes(planes, before, after, tiled, outer)


def plane_borders(planes: list[Any]) -> list[dict[str, Any]]:
    """The shared borders of tiled planes: ``{a, b, segment, length_ft, kind, step_ft, high}`` per pair and chain.

    ``segment`` is the polyline (points shared by both planes); ``kind`` is ``intersection`` (the two fitted planes meet
    along it within 1.5 ft: ridge, hip or valley) or ``step`` (they are further apart: a height step); ``step_ft`` is the
    median height of plane ``a`` above plane ``b`` along it and ``high`` the id of the higher plane.
    """
    out: list[dict[str, Any]] = []
    eqs = [plane_eq(p) for p in planes]
    shapes = [p.shape() for p in planes]
    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            if not shapes[i].intersects(shapes[j]):
                continue
            inter = shapes[i].boundary.intersection(shapes[j].boundary)
            lines = [g for g in getattr(inter, "geoms", [inter]) if g.geom_type == "LineString" and g.length >= 0.5]
            for line in lines:
                n = max(2, int(line.length) + 1)
                pts = [line.interpolate(k / (n - 1), normalized=True) for k in range(n)]
                gaps = sorted(z_at(eqs[i], q.x, q.y) - z_at(eqs[j], q.x, q.y) for q in pts)
                med = gaps[len(gaps) // 2]
                out.append({"a": planes[i].id, "b": planes[j].id, "segment": [[round(x, 2), round(y, 2)] for x, y in line.coords],
                            "length_ft": round(line.length, 1), "kind": "intersection" if abs(med) <= 1.5 else "step",
                            "step_ft": round(med, 2), "high": planes[i].id if med >= 0 else planes[j].id})
    return out


def _vertices(polys: list[Polygon]) -> int:
    return sum(len(r) for g in polys for r in _rings(g))


def straighten(planes: list[Any], footprint: Polygon | BaseGeometry | None = None, *, scales: tuple[float, ...] = BUDGET_SCALES) -> list[Any]:
    """``straighten_with_borders(...)[0]``."""
    return straighten_with_borders(planes, footprint, scales=scales)[0]


def straighten_with_borders(planes: list[Any], footprint: Polygon | BaseGeometry | None = None, *,
                            scales: tuple[float, ...] = BUDGET_SCALES) -> tuple[list[Any], list[dict[str, Any]]]:
    """The same planes with few-vertex outlines and straight shared borders; the input unchanged when that fails.

    ``planes`` are ``planes.Plane`` objects (disjoint, ideally tiling ``footprint``); ``footprint`` is the outline they
    tile (used only to find part of it no plane covers, which stays uncovered). Each returned plane has
    ``straightened`` True and ``raw_plan_area_sqft`` kept from the input (or set to the input's plan area); when the
    straightening fails its checks every plane is returned unchanged with ``straightened`` False (and one log line).
    """
    def finish(done: list[Any]) -> tuple[list[Any], list[dict[str, Any]]]:
        try:
            return done, plane_borders(done)
        except (ShapelyError, ValueError, TypeError, ArithmeticError, IndexError, KeyError):
            log.warning("plane borders failed", exc_info=True)
            return done, []

    def unchanged(why: str) -> tuple[list[Any], list[dict[str, Any]]]:
        log.info("planes not straightened: %s", why)
        return finish([replace(p, straightened=False, raw_plan_area_sqft=p.raw_plan_area_sqft if p.raw_plan_area_sqft is not None
                               else p.plan_area_sqft) for p in planes])

    def built_from(after: list[Polygon]) -> tuple[list[Any], list[dict[str, Any]]]:
        built = _build(planes, after)
        return finish([replace(b, raw_plan_area_sqft=p.raw_plan_area_sqft if p.raw_plan_area_sqft is not None
                               else p.plan_area_sqft) for b, p in zip(built, planes, strict=True)])

    if not planes:
        return [], []
    try:
        before = [_valid_grid(p.shape()) for p in planes]
        if any(not b.is_valid or b.is_empty for b in before):
            return unchanged("an input plane is not a valid polygon")
        tiled = unary_union(before)
        fp = footprint if footprint is not None and not footprint.is_empty else tiled
        voids = [g for g in polygons_of(fp.difference(tiled)) if g.area >= VOID_SQFT]
        if len(planes) == 1 and not voids:
            return finish([replace(planes[0], straightened=True, raw_plan_area_sqft=planes[0].raw_plan_area_sqft
                                   if planes[0].raw_plan_area_sqft is not None else planes[0].plan_area_sqft)])
        axis = _axis_deg(fp)
        dirs = [(axis + k * 45.0) % 180.0 for k in range(4)]
        why = "no attempt"
        for scale in scales:  # first choice: every border one straight roof line (ridge/hip/valley or a straight step)
            after, why_i = _attempt_geometric(planes, before, voids, tiled, scale, dirs, axis)
            if why_i is None:
                return built_from(after)
            why = why_i
            log.debug("roof lines at budget %.2f rejected: %s", scale, why_i)
        best: list[Polygon] | None = None
        for scale in scales:  # else the budgeted simplification: the fewest vertices that pass every check wins
            for turn in (False, True):
                after, why_i = _attempt(planes, before, voids, tiled, scale, dirs, turn)
                if why_i is None:
                    if best is None or _vertices(after) < _vertices(best):
                        best = after
                else:
                    why = why_i
                    log.debug("straightening at budget %.2f (turn %s) rejected: %s", scale, turn, why_i)
        if best is not None:
            return built_from(best)
        return unchanged(why)
    except (ShapelyError, ValueError, TypeError, ArithmeticError, IndexError, KeyError):
        log.warning("plane straightening failed", exc_info=True)
        return unchanged("an error")


building_axis_deg = _axis_deg  # public name: direction (0-180 degrees) of the outline's long side
