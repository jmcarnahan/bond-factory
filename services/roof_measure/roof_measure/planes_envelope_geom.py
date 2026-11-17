"""Geometry helpers for ``planes_envelope``: building axes, square plane equations, roof lines and cell cleanup (internal).

Pure shapely and arithmetic on the planes' own feet frame (x east, y north). Directions of lines are math angles in
degrees modulo 180; a plane's facing (downslope) is a math angle modulo 360.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, nearest_points, unary_union

from .classify import polygons_of

Eq = tuple[float, float, float]  # z = a x + b y + c (feet above ground, plan feet)
Pt = tuple[float, float]

SQUARE_FACING_DEG = 10.0  # a facing this near a building axis is set onto it (roofs are built square)
TURN_DEG = 8.0  # an intersection line this near an axis or a 45-degree diagonal is turned onto it
STEP_SNAP_DEG = 25.0  # a step border this near an axis runs along it
L_FIT_FT = 2.0  # a step border that leaves points further than this from one line becomes two axis segments
FAR_FT = 400.0  # half-length of an "infinite" line before it is cut to the region
END_SLACK_FT = 3.0  # the ends of a step border this long are not held to the straight-line test
ON_OUTLINE_FT = 1.5  # a border end this near the outline is on it
L_REACH_FT = 3.0  # a step chord reaches this far past the border's end points (and an L's legs past their corner)
SHORT_STEP_FT = 6.0  # a step border shorter than this has no reliable direction of its own: it runs along an axis


def axis_deg(outline: BaseGeometry) -> float:
    """Direction (0-180) of the building's u axis: the dominant wall direction (outline edges, length-weighted, folded
    modulo 90 degrees), turned to whichever of it and its perpendicular is nearer the long side of the minimum rotated
    rectangle. On a rectangle-ish outline this IS the long side; on a plus- or L-shaped outline the rectangle can sit
    at 45 degrees to every wall, so the walls decide."""
    parts = polygons_of(outline)
    if not parts:
        return 0.0
    poly = max(parts, key=lambda p: p.area)
    pts = list(poly.minimum_rotated_rectangle.exterior.coords)
    rect = 0.0
    if len(pts) >= 5:
        a, b, c = pts[0], pts[1], pts[2]
        e = (b[0] - a[0], b[1] - a[1]) if math.dist(a, b) >= math.dist(b, c) else (c[0] - b[0], c[1] - b[1])
        rect = math.degrees(math.atan2(e[1], e[0])) % 180.0
    ring = list(poly.exterior.coords)
    edges = [(math.hypot(x1 - x0, y1 - y0), math.degrees(math.atan2(y1 - y0, x1 - x0)) % 90.0)
             for (x0, y0), (x1, y1) in itertools.pairwise(ring)]
    edges = [(ln, d) for ln, d in edges if ln > 0]
    if not edges:
        return rect
    # the wall direction (modulo 90) with the most wall length within 3 degrees of it; then the length-weighted mean of
    # those walls (angles times 4 make the modulo-90 mean a plain circular mean)
    peak = max(range(180), key=lambda k: (sum(ln for ln, d in edges if ang_diff(d, k / 2.0, 90.0) <= 3.0), -k)) / 2.0
    near = [(ln, d) for ln, d in edges if ang_diff(d, peak, 90.0) <= 3.0]
    cx = sum(ln * math.cos(math.radians(4 * d)) for ln, d in near)
    cy = sum(ln * math.sin(math.radians(4 * d)) for ln, d in near)
    wall = (math.degrees(math.atan2(cy, cx)) / 4.0) % 90.0
    return min((wall, (wall + 90.0) % 180.0), key=lambda a: ang_diff(a, rect))


def ang_diff(a: float, b: float, period: float = 180.0) -> float:
    d = abs(a - b) % period
    return min(d, period - d)


def z_at(eq: Eq, x: float, y: float) -> float:
    return eq[0] * x + eq[1] * y + eq[2]


def eq_of(plane: Any) -> Eq:
    """The plane's equation: its ``plane_eq`` when present, else from pitch, facing and height at the centroid."""
    eq = getattr(plane, "plane_eq", None)
    if eq is not None:
        return float(eq[0]), float(eq[1]), float(eq[2])
    s = float(plane.pitch_rise) / 12.0 if plane.aspect_deg is not None else 0.0
    a = math.radians(float(plane.aspect_deg or 0.0))
    gx, gy = -s * math.sin(a), -s * math.cos(a)
    c = Polygon(plane.polygon).centroid
    return gx, gy, float(plane.height_ft) - gx * c.x - gy * c.y


def square_eq(eq: Eq, anchor: BaseGeometry, u_deg: float) -> tuple[Eq, float, float]:
    """``eq`` with its facing set onto the nearest building axis when within ``SQUARE_FACING_DEG``.

    The slope is kept and ``c`` re-fitted so the plane keeps its mean height over ``anchor`` (a planar height's mean
    over a polygon is its height at the centroid). Returns the equation, the turn (degrees) and the largest height
    change over ``anchor``'s outline (feet).
    """
    gx, gy, _ = eq
    s = math.hypot(gx, gy)
    if s < 1e-6 or anchor.is_empty:
        return eq, 0.0, 0.0
    down = math.degrees(math.atan2(-gy, -gx)) % 360.0
    best = min(((u_deg + 90.0 * k) % 360.0 for k in range(4)), key=lambda t: ang_diff(down, t, 360.0))
    turn = ang_diff(down, best, 360.0)
    if turn > SQUARE_FACING_DEG or turn < 1e-9:
        return eq, 0.0, 0.0
    r = math.radians(best)
    nx, ny = -s * math.cos(r), -s * math.sin(r)
    cen = anchor.centroid
    z0 = z_at(eq, cen.x, cen.y)
    new = (nx, ny, z0 - nx * cen.x - ny * cen.y)
    ring = [q for g in polygons_of(anchor) for q in g.exterior.coords] or [(cen.x, cen.y)]
    moved = max(abs(z_at(new, x, y) - z_at(eq, x, y)) for x, y in ring)
    return new, turn, moved


def aspect_of(eq: Eq) -> float | None:
    """Compass bearing (0 = north, 90 = east) of the downslope direction; None for a flat plane."""
    if math.hypot(eq[0], eq[1]) < 1e-6:
        return None
    return round((math.degrees(math.atan2(-eq[0], -eq[1]))) % 360.0, 1)


def meet_line(e1: Eq, e2: Eq, anchor: Pt, dirs: list[float], min_grad: float) -> tuple[Pt, Pt] | None:
    """Where two planes have the same height: (point nearest ``anchor``, unit direction), turned onto a dominant
    direction within ``TURN_DEG`` about that point; None for near-parallel planes."""
    p, q, r = e1[0] - e2[0], e1[1] - e2[1], e1[2] - e2[2]
    g2 = p * p + q * q
    if math.sqrt(g2) < min_grad:
        return None
    t = (p * anchor[0] + q * anchor[1] + r) / g2
    px, py = anchor[0] - t * p, anchor[1] - t * q
    d = math.degrees(math.atan2(p, -q)) % 180.0
    near = min(dirs, key=lambda a: ang_diff(d, a))
    if ang_diff(d, near) <= TURN_DEG:
        d = near
    rd = math.radians(d)
    return (px, py), (math.cos(rd), math.sin(rd))


def anchor_between(a: BaseGeometry, b: BaseGeometry) -> Pt:
    """The middle of where two raw clusters meet: centroid of their 3 ft neighbourhoods' overlap, else the midpoint
    of their nearest points."""
    both = a.buffer(3.0).intersection(b.buffer(3.0))
    if not both.is_empty and both.area > 0:
        c = both.centroid
        return c.x, c.y
    p1, p2 = nearest_points(a, b)
    return (p1.x + p2.x) / 2, (p1.y + p2.y) / 2


def merge_lines(g: BaseGeometry) -> BaseGeometry:
    """The line parts of ``g`` joined where they touch (a single line comes back as it is)."""
    lines = [q for q in getattr(g, "geoms", [g]) if q.geom_type in ("LineString", "MultiLineString")]
    if not lines:
        return LineString()
    u = unary_union(lines)
    return u if u.geom_type == "LineString" else linemerge(u)


def straight_runs(line: BaseGeometry, tol_deg: float = 3.0) -> list[LineString]:
    """A polyline cut into its straight runs (a bend over ``tol_deg`` starts a new run)."""
    if line.geom_type != "LineString" or len(line.coords) < 2:
        return []
    pts = list(line.coords)
    runs, cur = [], [pts[0], pts[1]]
    for q in pts[2:]:
        a, b = cur[-2], cur[-1]
        d1 = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        d2 = math.degrees(math.atan2(q[1] - b[1], q[0] - b[0]))
        if ang_diff(d1, d2, 360.0) > tol_deg:
            runs.append(LineString(cur))
            cur = [b, q]
        else:
            cur.append(q)
    runs.append(LineString(cur))
    return runs


def long_line(p: Pt, d: Pt) -> LineString:
    return LineString([(p[0] - FAR_FT * d[0], p[1] - FAR_FT * d[1]), (p[0] + FAR_FT * d[0], p[1] + FAR_FT * d[1])])


def sample_line(g: BaseGeometry, step: float = 1.0) -> list[Pt]:
    """Points every ``step`` feet along every line part of ``g`` (in order, parts one after another)."""
    out: list[Pt] = []
    for part in getattr(g, "geoms", [g]):
        if part.geom_type != "LineString" or part.length <= 0:
            continue
        n = max(2, int(part.length / step) + 1)
        out += [(q.x, q.y) for q in (part.interpolate(i / (n - 1), normalized=True) for i in range(n))]
    return out


def _axis_fit(pts: list[Pt], deg: float) -> tuple[Pt, Pt, float]:
    """Line with direction ``deg`` at the points' median offset: (point, direction, worst distance)."""
    r = math.radians(deg)
    d = (math.cos(r), math.sin(r))
    offs = sorted(-d[1] * x + d[0] * y for x, y in pts)
    off = offs[len(offs) // 2]
    p = (-d[1] * off, d[0] * off)
    worst = max(abs(-d[1] * x + d[0] * y - off) for x, y in pts)
    return p, d, worst


def _inner_worst(pts: list[Pt], p: Pt, d: Pt) -> float:
    """The worst distance of the points from the line, ignoring the first and last ``END_SLACK_FT`` of a long border
    (a gap-filled border bends at its ends to reach an outline corner; that bend is not a second wall)."""
    run = [0.0]
    for a, b in itertools.pairwise(pts):
        run.append(run[-1] + math.dist(a, b))
    total = run[-1]
    keep = [q for q, s in zip(pts, run, strict=True) if total < 3 * END_SLACK_FT or END_SLACK_FT <= s <= total - END_SLACK_FT]
    return max(abs(-d[1] * (x - p[0]) + d[0] * (y - p[1])) for x, y in (keep or pts))


def step_path(pts: list[Pt], u_deg: float) -> list[tuple[Pt, Pt]]:
    """A step border as one straight line (snapped to u or v within ``STEP_SNAP_DEG``) or, when that line leaves a
    point more than ``L_FIT_FT`` away, the best two-segment axis path. Returns the lines as (point, direction)."""
    if len(pts) < 2:
        return []
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    deg = math.degrees(0.5 * math.atan2(2 * sxy, sxx - syy)) % 180.0
    near = min((u_deg % 180.0, (u_deg + 90.0) % 180.0), key=lambda a: ang_diff(deg, a))
    span = math.dist(pts[0], pts[-1])
    if ang_diff(deg, near) <= STEP_SNAP_DEG or span < SHORT_STEP_FT:
        deg = near
    p, d, _ = _axis_fit(pts, deg)
    worst = _inner_worst(pts, p, d)
    if worst <= L_FIT_FT or len(pts) < 6:
        return [(p, d)]
    best: tuple[float, list[tuple[Pt, Pt]]] = (worst, [(p, d)])
    axes = (u_deg % 180.0, (u_deg + 90.0) % 180.0)
    for k in range(3, len(pts) - 2):
        for a1, a2 in ((axes[0], axes[1]), (axes[1], axes[0])):
            p1, d1, w1 = _axis_fit(pts[:k], a1)
            p2, d2, w2 = _axis_fit(pts[k:], a2)
            if max(w1, w2) < best[0] - 1e-9:
                best = (max(w1, w2), [(p1, d1), (p2, d2)])
    return best[1]


def _to_outline(p: Pt, d: Pt, t0: float, t1: float, outline: BaseGeometry, ends: tuple[Pt, Pt] | None = None) -> tuple[float, float]:
    """The span [t0, t1] along the line p + t d widened at each end to the outline: to the crossing nearest the
    border's own end point when that end is on the outline (so the line stops where the border did), else to the
    first crossing beyond the span (``L_REACH_FT`` when there is none)."""
    cut = long_line(p, d).intersection(outline)
    ts = sorted((q.x - p[0]) * d[0] + (q.y - p[1]) * d[1] for q in getattr(cut, "geoms", [cut]) if q.geom_type == "Point")
    out = []
    for k, (t, other, side) in enumerate(((t0, t1, -1.0), (t1, t0, 1.0))):
        end = ends[k] if ends is not None else None
        ahead = [s for s in ts if (s - other) * side > 0]  # crossings on this end's side of the other end
        if end is not None and ahead and outline.distance(Point(end)) <= ON_OUTLINE_FT:
            near = min(ahead, key=lambda s: math.dist((p[0] + s * d[0], p[1] + s * d[1]), end))
            out.append(near + side * 0.5)
            continue
        beyond = [s for s in ts if (s - t) * side >= -1e-6]
        out.append((min(beyond, key=lambda s: abs(s - t)) + side * 0.5) if beyond else t + side * L_REACH_FT)
    return out[0], out[1]


def l_segments(lines: list[tuple[Pt, Pt]], pts: list[Pt], outline: BaseGeometry) -> list[LineString]:
    """The step lines as chords: a straight step covers the border's span and runs on to the outline at both ends
    (no further: past it the line would cut through the next roof); an L is two legs that cross at the corner and
    run from it past the border's end points to the outline."""
    if len(lines) == 1:
        p, d = lines[0]
        ta, tb = ((q[0] - p[0]) * d[0] + (q[1] - p[1]) * d[1] for q in (pts[0], pts[-1]))
        ends = (pts[0], pts[-1]) if ta <= tb else (pts[-1], pts[0])
        t0, t1 = _to_outline(p, d, min(ta, tb), max(ta, tb), outline, ends)
        return [LineString([(p[0] + t0 * d[0], p[1] + t0 * d[1]), (p[0] + t1 * d[0], p[1] + t1 * d[1])])]
    (p1, d1), (p2, d2) = lines
    det = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / det
    c = (p1[0] + t * d1[0], p1[1] + t * d1[1])
    out = []
    for end, d in ((pts[0], d1), (pts[-1], d2)):
        along = (end[0] - c[0]) * d[0] + (end[1] - c[1]) * d[1]
        sd = (d[0], d[1]) if along >= 0 else (-d[0], -d[1])
        _, t1 = _to_outline(c, sd, 0.0, abs(along), outline, (c, end))
        tip = (c[0] + t1 * sd[0], c[1] + t1 * sd[1])
        if outline.distance(Point(end)) <= ON_OUTLINE_FT and math.dist(tip, end) > 2 * ON_OUTLINE_FT:
            # the leg runs on far past where the border met the outline: the L was a poor reading; one line instead
            long_leg = d1 if math.dist(pts[0], c) >= math.dist(pts[-1], c) else d2
            p, dd, _ = _axis_fit(pts, math.degrees(math.atan2(long_leg[1], long_leg[0])) % 180.0)
            return l_segments([(p, dd)], pts, outline)
        out.append(LineString([(c[0] - L_REACH_FT * sd[0], c[1] - L_REACH_FT * sd[1]), tip]))
    return out
