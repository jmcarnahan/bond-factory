"""Roof lines for the border between two planes: ridge, hip and valley from the fitted planes, or a straight step (internal).

Used by ``planes_straight``. For two adjacent planes ``z = a1 x + b1 y + c1`` and ``z = a2 x + b2 y + c2`` the plan line where
the heights agree is the ridge, hip or valley between them; when the planes are far apart in height along their border
(a step between a higher and a lower roof section) there is no such line and the border is ONE straight line fitted to
the existing border, its direction turned onto the building's axes. ``geometric`` moves a net onto those lines.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Polygon

from .planes_net import MAX_PLANE_DRIFT, MIN_DRIFT_SQFT, _chains, _diff_deg, _Net

MEET_FT = 1.5  # planes meet (an intersection line is the border) when the median height gap along the border is below this
MAX_LINE_DIST_FT = 2.5  # ... and the line is within this mean distance of the existing border
MAX_STEP_DIST_FT = 2.0  # a fitted step line may be at most this mean distance from the existing border
MIN_GRADIENT_DIFF = 0.02  # two planes whose slopes differ by less than this have no usable intersection line
TURN_DEG = 8.0  # an intersection line within this of a dominant direction is turned onto it
STEP_45_DEG = 10.0  # a step line is turned onto 45 degrees only when within this of it
MAX_JUNCTION_MOVE_FT = 3.0
SAMPLE_FT = 1.0

Line = tuple[tuple[float, float], tuple[float, float]]  # a point on the line and its unit direction


def plane_eq(plane: Any) -> tuple[float, float, float]:
    """``(a, b, c)`` of ``z = a x + b y + c`` (feet above ground); derived from pitch, aspect and height when the
    plane carries no ``plane_eq``: the height is taken at the polygon's centroid."""
    eq = getattr(plane, "plane_eq", None)
    if eq is not None:
        return float(eq[0]), float(eq[1]), float(eq[2])
    s = float(plane.pitch_rise) / 12.0 if plane.aspect_deg is not None else 0.0
    a = math.radians(float(plane.aspect_deg or 0.0))
    gx, gy = -s * math.sin(a), -s * math.cos(a)
    xs = [p[0] for p in plane.polygon]
    ys = [p[1] for p in plane.polygon]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    return gx, gy, float(plane.height_ft) - gx * cx - gy * cy


def z_at(eq: tuple[float, float, float], x: float, y: float) -> float:
    return eq[0] * x + eq[1] * y + eq[2]


def _samples(net: _Net, chain: list[int]) -> list[tuple[float, float]]:
    line = LineString([tuple(net.pos[v]) for v in chain])
    n = max(2, int(line.length / SAMPLE_FT) + 1)
    return [(p.x, p.y) for p in (line.interpolate(i / (n - 1), normalized=True) for i in range(n))]


def _dist(p: tuple[float, float], line: Line) -> float:
    (cx, cy), (dx, dy) = line
    return abs(dx * (p[1] - cy) - dy * (p[0] - cx))


def _turned(line: Line, pts: list[tuple[float, float]], target_deg: float) -> Line:
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    # keep the point of the line nearest the border's middle, rotate about it
    (cx, cy), (dx, dy) = line
    t = (mx - cx) * dx + (my - cy) * dy
    px, py = cx + t * dx, cy + t * dy
    r = math.radians(target_deg)
    return (px, py), (math.cos(r), math.sin(r))


def _angle(d: tuple[float, float]) -> float:
    return math.degrees(math.atan2(d[1], d[0])) % 180.0


def intersection_line(eq_a: tuple[float, float, float], eq_b: tuple[float, float, float],
                      pts: list[tuple[float, float]], dirs: list[float]) -> Line | None:
    """The ridge/hip/valley line of two planes for a border sampled at ``pts``; None when they do not meet there."""
    p, q, r = eq_a[0] - eq_b[0], eq_a[1] - eq_b[1], eq_a[2] - eq_b[2]
    g = math.hypot(p, q)
    if g < MIN_GRADIENT_DIFF:
        return None
    gaps = sorted(abs(p * x + q * y + r) for x, y in pts)
    if gaps[len(gaps) // 2] > MEET_FT:
        return None
    nx, ny = p / g, q / g
    line: Line = ((-nx * r / g, -ny * r / g), (-ny, nx))
    if sum(_dist(pt, line) for pt in pts) / len(pts) > MAX_LINE_DIST_FT:
        return None
    best = min(dirs, key=lambda d: _diff_deg(_angle(line[1]), d))
    if _diff_deg(_angle(line[1]), best) <= TURN_DEG:
        line = _turned(line, pts, best)
    # the DIRECTION is the roof's (the planes meet along it); the POSITION is where the border was measured, which is
    # better known than the intersection of two fitted planes (a 0.3 ft height error is 1-2 ft of position at 3/12)
    (cx, cy), (dx, dy) = line
    offs = sorted(dx * (y - cy) - dy * (x - cx) for x, y in pts)
    off = offs[len(offs) // 2]
    line = ((cx - dy * off, cy + dx * off), (dx, dy))
    if sum(_dist(pt, line) for pt in pts) / len(pts) > MAX_STEP_DIST_FT:
        return None
    return line


def step_line(pts: list[tuple[float, float]], axis: float) -> Line | None:
    """One straight line through the border (least squares), turned onto the building axes (0 and 90 degrees in the
    building frame; 45 only when within STEP_45_DEG of it); the plain fit when the turned line strays too far."""
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    if sxx + syy < 1e-9:
        return None
    th = 0.5 * math.atan2(2 * sxy, sxx - syy)
    fit: Line = ((mx, my), (math.cos(th), math.sin(th)))
    off = (_angle(fit[1]) - axis) % 90.0  # angle from the building axis
    if abs(off - 45.0) <= STEP_45_DEG:  # the 45 that is nearest the fit (there are two: +45 and +135)
        cands = [(axis + 45.0) % 180.0, (axis + 135.0) % 180.0]
    else:
        cands = [axis % 180.0, (axis + 90.0) % 180.0]
    t = min(cands, key=lambda c: _diff_deg(_angle(fit[1]), c))
    turned = _turned(fit, pts, t)
    if sum(_dist(p, turned) for p in pts) / n <= MAX_STEP_DIST_FT:
        return turned
    if sum(_dist(p, fit) for p in pts) / n <= MAX_STEP_DIST_FT:
        return fit
    return None


def _swept_area(net: _Net, chain: list[int], line: Line) -> float:
    """Area between the border and the straight segment that replaces it (the ends projected onto the line)."""
    (cx, cy), (dx, dy) = line
    ends = []
    for v in (chain[0], chain[-1]):
        x, y = net.pos[v]
        t = (x - cx) * dx + (y - cy) * dy
        ends.append((cx + t * dx, cy + t * dy))
    ring = [tuple(net.pos[v]) for v in chain] + [ends[1], ends[0]]
    return float(Polygon(ring).buffer(0).area) if len(ring) >= 4 else 0.0


def _owners(net: _Net) -> dict[tuple[int, int], list[int]]:
    out: dict[tuple[int, int], list[int]] = {}
    for n, rr in enumerate(net.rings):
        for ids in rr:
            for i, a in enumerate(ids):
                b = ids[(i + 1) % len(ids)]
                out.setdefault((min(a, b), max(a, b)), []).append(n)
    return out


def _junctions(net: _Net, accepted: list[tuple[list[int], Line]]) -> tuple[dict[int, list[float]], tuple[list[int], Line] | None]:
    """Where each junction goes (the point nearest all its border lines); the second item is the accepted border to
    give up when some junction would move more than MAX_JUNCTION_MOVE_FT, else None."""
    at: dict[int, list[tuple[list[int], Line]]] = {}
    for item in accepted:
        for v in (item[0][0], item[0][-1]):
            at.setdefault(v, []).append(item)
    new: dict[int, list[float]] = {}
    for v, items in at.items():
        if v in net.fixed:
            continue
        lines = [ln for _, ln in items]
        x0, y0 = net.pos[v]
        if v in net.slide:
            (ax, ay), (bx, by) = net.slide[v]
            ln = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / ln, (by - ay) / ln
            num = den = 0.0
            for (cx, cy), (dx, dy) in lines:
                nx, ny = -dy, dx
                k = nx * ux + ny * uy
                num += k * (nx * (ax - cx) + ny * (ay - cy))
                den += k * k
            if den < 1e-6:
                continue
            t = max(0.0, min(ln, -num / den))
            p = [ax + t * ux, ay + t * uy]
        else:
            m00 = m01 = m11 = b0 = b1 = 0.0
            for (cx, cy), (dx, dy) in lines:
                nx, ny = -dy, dx
                m00 += nx * nx
                m01 += nx * ny
                m11 += ny * ny
                c = nx * cx + ny * cy
                b0 += nx * c
                b1 += ny * c
            lam = 0.02 * len(lines)  # a light pull towards where the vertex is, for near-parallel lines
            m00 += lam
            m11 += lam
            b0 += lam * x0
            b1 += lam * y0
            det = m00 * m11 - m01 * m01
            p = [(b0 * m11 - b1 * m01) / det, (m00 * b1 - m01 * b0) / det]
        if math.dist(p, (x0, y0)) > MAX_JUNCTION_MOVE_FT:
            return {}, max(items, key=lambda it: _dist((x0, y0), it[1]))
        new[v] = p
    return new, None


def geometric(net: _Net, planes: list[Any], dirs: list[float], axis: float, scale: float = 1.0) -> str | None:
    """Move the net so every border between two planes is ONE straight roof line (see the module doc), dropping the
    border's other vertices. Borders that fit neither kind of line (or whose junction
    would jump too far) stay as they are. Returns None (reserved for a reason it cannot)."""
    owners = _owners(net)
    eqs = [plane_eq(p) for p in planes]
    accepted: list[tuple[list[int], Line]] = []
    budget = [scale * max(MAX_PLANE_DRIFT * net.ring_area(n), MIN_DRIFT_SQFT) for n in range(len(net.rings))]
    chains = _chains(net)
    chains.sort(key=lambda c: -sum(math.dist(net.pos[c[i]], net.pos[c[i + 1]]) for i in range(len(c) - 1)))
    for ch in chains:
        if ch[0] == ch[-1] or len(ch) < 2:
            continue
        own = owners.get((min(ch[0], ch[1]), max(ch[0], ch[1])), [])
        if len(own) != 2:
            continue
        pts = _samples(net, ch)
        line = None
        if own[0] < len(planes) and own[1] < len(planes):
            line = intersection_line(eqs[own[0]], eqs[own[1]], pts, dirs)
        if line is None:
            line = step_line(pts, axis)
        if line is None:
            continue
        cost = _swept_area(net, ch, line)  # the area the straight line moves between the two planes: both pay for it
        if all(cost <= budget[n] for n in own):
            for n in own:
                budget[n] -= cost
            accepted.append((ch, line))
    while True:  # a junction that would jump too far loses its worst-fitting line (that border is simplified instead)
        moved, worst = _junctions(net, accepted)
        if worst is None:
            break
        accepted.remove(worst)
    for v, p in moved.items():
        net.pos[v] = p
    net.drop({v for ch, _ in accepted for v in ch[1:-1]})
    return None
