"""The never-worse gate for ``planes_envelope`` (internal): None when the new planes may replace the input, else why not.

Per-plane area budget: a plane's EXPECTED plan area is its raw LiDAR cluster (inside the outline) grown by its share
of the uncovered outline, where each uncovered square foot belongs to the NEAREST raw cluster
(``expected = raw + uncovered nearest to raw``, sampled on a 1 ft grid). The new area must be within ``PLANE_SHARE``
(35%) of that, or ``PLANE_SLACK_SQFT``, or ``SHIFT_FT`` times the length of its borders with other planes (a
small plane is mostly border: moving its borders by 1.5 ft is a big share of its area, not a wrong roof). Why nearest and not proportional: a plane can only grow into
the bare roof next to it (a flat roof whose cluster is a blob in the middle owns the bare roof around it; a small
plane does not own a share of a far corner). Gap filling is NOT the reference: it is the arbitrary part this step
replaces.

Vertices: at most ``MAX_VERTICES`` per plane that are not on the outline (vertices on the outline are its corners
or where a border meets it, which the outline contributes), or ``PER_NEIGHBOUR`` per plane it borders when that is
more (each neighbour's border brings its own two ends).
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry

PLAN_SHARE = 0.01  # total plan area vs the outline
SURFACE_SHARE = 0.05  # total surface area vs the input planes
PLANE_SHARE = 0.35
PLANE_SLACK_SQFT = 10.0
SHIFT_FT = 1.5  # ... or every border it shares with other planes moved by this much (small planes: mostly border)
LOSE_OK_SQFT = 25.0  # a plane whose raw cluster is under this may vanish (merged into a neighbour)
MAX_VERTICES = 10  # vertices that are not on the outline ...
PER_NEIGHBOUR = 2  # ... or two per neighbouring plane, whichever is more (a flat roof ringed by eight small slopes)
MIN_ANGLE_DEG = 10.0
MIN_EDGE_FT = 0.5  # an edge shorter than this away from the outline is a stub
CORNER_FT = 0.05
MAX_OVERLAP_SQFT = 0.5


def _surface(area: float, pitch: float) -> float:
    return area / math.cos(math.atan(pitch / 12.0))


def _angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))))


def _on(ob: BaseGeometry, a: tuple[float, float], b: tuple[float, float]) -> bool:
    return bool(ob.distance(Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) < 0.02)


def _sharp_outline_corner(fp: Polygon, b: tuple[float, float]) -> bool:
    """True when ``b`` is a corner of the outline that is itself sharper than ``MIN_ANGLE_DEG`` (not ours to fix)."""
    pts = list(fp.exterior.coords)[:-1]
    for k, q in enumerate(pts):
        if math.dist(q, b) < CORNER_FT:
            return _angle(pts[k - 1], q, pts[(k + 1) % len(pts)]) < MIN_ANGLE_DEG
    return False


def _shape_problem(pid: str, g: Polygon, fp: Polygon, neighbours: int = 0) -> str | None:
    if not g.is_valid or g.is_empty or not g.exterior.is_simple:
        return f"plane {pid} is not a valid simple polygon"
    ob = fp.exterior
    count = 0
    for ring in [g.exterior, *g.interiors]:
        pts = list(ring.coords)[:-1]
        for i, b in enumerate(pts):
            a, c = pts[i - 1], pts[(i + 1) % len(pts)]
            if ob.distance(Point(b)) > CORNER_FT:
                count += 1
            if _angle(a, b, c) < MIN_ANGLE_DEG and not _sharp_outline_corner(fp, b):
                return f"plane {pid} has a {_angle(a, b, c):.1f} degree spike"
            if math.dist(b, c) < MIN_EDGE_FT and not (ob.distance(Point(b)) < MIN_EDGE_FT and ob.distance(Point(c)) < MIN_EDGE_FT):
                return f"plane {pid} has a {math.dist(b, c):.2f} ft edge inside the roof"
    if count > max(MAX_VERTICES, PER_NEIGHBOUR * neighbours):
        return f"plane {pid} has {count} vertices"
    return None


def expected_areas(ids: list[str], raws: list[BaseGeometry], fp: Polygon, step: float = 1.0) -> dict[str, float]:
    """Each plane's raw area inside ``fp`` plus the uncovered part of ``fp`` nearest its cluster (1 ft grid)."""
    import numpy as np
    import shapely

    out = {pid: float(r.area) for pid, r in zip(ids, raws, strict=True)}
    live = [(pid, r) for pid, r in zip(ids, raws, strict=True) if not r.is_empty and r.area > 0]
    if not live:
        return out
    bare = fp.difference(shapely.unary_union([r for _, r in live]))
    if bare.is_empty:
        return out
    x0, y0, x1, y1 = bare.bounds
    xs, ys = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
    pts = shapely.points(xs.ravel(), ys.ravel())
    pts = pts[shapely.contains(bare, pts)]
    if len(pts) == 0:
        return out
    dist = np.stack([shapely.distance(r, pts) for _, r in live])
    near = np.argmin(dist, axis=0)
    cell = bare.area / len(pts)
    for k, (pid, _) in enumerate(live):
        out[pid] += float((near == k).sum()) * cell
    return out


def gate(before: list[Any], after: list[Any], raws: list[BaseGeometry], fp: Polygon, merged_small: list[str]) -> str | None:
    """None when ``after`` may replace ``before``; ``raws`` are the input planes' raw clusters inside ``fp``."""
    raw_of = {p.id: r for p, r in zip(before, raws, strict=True)}
    for pid in merged_small:
        if raw_of[pid].area >= LOSE_OK_SQFT:
            return f"plane {pid} vanished"
    shapes = [Polygon(p.polygon, p.holes) for p in after]
    plan = sum(g.area for g in shapes)
    if abs(plan - fp.area) > PLAN_SHARE * fp.area:
        return f"plan area {plan:.0f} vs outline {fp.area:.0f}"
    sb = sum(_surface(Polygon(p.polygon, p.holes).area, float(p.pitch_rise)) for p in before)
    sa = sum(_surface(g.area, float(p.pitch_rise)) for p, g in zip(after, shapes, strict=True))
    if sb > 0 and abs(sa - sb) > SURFACE_SHARE * sb:
        return f"surface area {100 * (sa - sb) / sb:+.1f}%"
    grown = expected_areas([p.id for p in before], raws, fp)
    for p, g in zip(after, shapes, strict=True):
        nb = sum(1 for o in shapes if o is not g and g.distance(o) < 1e-6 and g.boundary.intersection(o.boundary).length > 0.5)
        why = _shape_problem(p.id, g, fp, nb)
        if why:
            return why
        expected = grown.get(p.id, 0.0)
        inner = g.exterior.length - g.exterior.intersection(fp.exterior.buffer(CORNER_FT)).length  # its borders with planes
        allowed = max(PLANE_SHARE * expected, PLANE_SLACK_SQFT, SHIFT_FT * inner)
        if raw_of[p.id].area > 0 and abs(g.area - expected) > allowed:
            return f"plane {p.id} area {g.area:.0f} vs expected {expected:.0f}"
    worst = max((a.intersection(b).area for i, a in enumerate(shapes) for b in shapes[i + 1:]), default=0.0)
    if worst > MAX_OVERLAP_SQFT:
        return f"overlap {worst:.2f} sq ft"
    return None
