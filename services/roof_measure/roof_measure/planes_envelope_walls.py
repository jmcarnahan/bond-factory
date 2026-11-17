"""Step lines meeting walls for ``planes_envelope_steps`` (internal): a step line that runs a few inches beside a
parallel outline wall continues that wall (``onto_walls``); a step whose border meets the outline away from the line
turns a corner to meet it there (``_legs``); parallel step lines of one border a foot or two apart, end to end, are
one wall (``_one_wall``).
"""

from __future__ import annotations

import itertools
import math

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .planes_envelope_geom import ang_diff, l_segments

Pt = tuple[float, float]
Line = tuple[Pt, Pt]

WALL_SNAP_FT = 0.5  # a step line parallel to an outline wall and this close to its line continues that wall
WALL_DEG = 2.0  # ... parallel: within this many degrees
WALL_NEAR_FT = 1.5  # ... and the wall reaches this near one end of the step's border
MEASURED_END_FT = 2.5  # a border end this near the measured border (touch points) is measured
STAIR_MISS_FT = 3.0  # a step line that meets the outline this far from where its border does misses a corner
ALIGN_FT = 2.5  # parallel step lines of one border this near each other, end to end, are one wall


def _deg(d: Pt) -> float:
    return math.degrees(math.atan2(d[1], d[0])) % 180.0


def onto_walls(lines: list[Line], pts: list[Pt], outline: BaseGeometry) -> list[Line]:
    """Each step line (point, unit direction) moved onto the line of an outline wall that is parallel to it, within
    ``WALL_SNAP_FT`` of it, and reaches within ``WALL_NEAR_FT`` of an end of the step's border ``pts``."""
    if not pts:
        return lines
    ends = [Point(pts[0]), Point(pts[-1])]
    ring: list[tuple[float, float]] = []
    for part in getattr(outline, "geoms", [outline]):
        ring += list(part.coords)
    walls = [(a, b) for a, b in itertools.pairwise(ring) if math.dist(a, b) > 1.0]
    out = []
    for p, d in lines:
        deg = math.degrees(math.atan2(d[1], d[0]))
        best: tuple[float, Line] | None = None
        for a, b in walls:
            if ang_diff(deg, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))) > WALL_DEG:
                continue
            if min(LineString([a, b]).distance(e) for e in ends) > WALL_NEAR_FT:
                continue
            off = -d[1] * (a[0] - p[0]) + d[0] * (a[1] - p[1])
            if abs(off) <= WALL_SNAP_FT and (best is None or abs(off) < abs(best[0])):
                ln = math.dist(a, b)
                wd = ((b[0] - a[0]) / ln, (b[1] - a[1]) / ln)
                best = (off, ((a[0], a[1]), wd if wd[0] * d[0] + wd[1] * d[1] >= 0 else (-wd[0], -wd[1])))
        out.append((p, d) if best is None else best[1])  # the wall's own line
    return out


def _legs(lines: list[Line], pts: list[Pt], fp: Polygon, touch: list[Pt]) -> list[LineString]:
    """The chords of a step line whose border ends on the outline away from the line where the clusters were
    measured side by side (a wall that turns a corner to meet the outline where the border does): the line stops at the foot of that end and a perpendicular leg runs
    from there through the end to the outline. Other ends, and every L, as ``l_segments`` draws them."""
    chords = l_segments(lines, pts, fp.boundary)
    if len(lines) != 1 or len(chords) != 1:
        return chords
    (p, d), ob = lines[0], fp.exterior
    seg = chords[0]
    a, b = seg.coords[0], seg.coords[-1]
    ta, tb = ((q[0] - p[0]) * d[0] + (q[1] - p[1]) * d[1] for q in (a, b))
    legs = []
    for e in (pts[0], pts[-1]):
        off = -d[1] * (e[0] - p[0]) + d[0] * (e[1] - p[1])
        if ob.distance(Point(e)) > WALL_NEAR_FT or abs(off) <= STAIR_MISS_FT / 2:
            continue
        if not touch or min(math.dist(e, q) for q in touch) > MEASURED_END_FT:
            continue  # the gap fill put this end there, not a measurement
        t = (e[0] - p[0]) * d[0] + (e[1] - p[1]) * d[1]
        foot = (p[0] + t * d[0], p[1] + t * d[1])
        n = (-d[1], d[0]) if off > 0 else (d[1], -d[0])
        far = LineString([foot, (foot[0] + n[0] * 400.0, foot[1] + n[1] * 400.0)]).intersection(ob)
        hits = [(g.x, g.y) for g in getattr(far, "geoms", [far]) if g.geom_type == "Point"]
        if not hits:
            continue
        end = min(hits, key=lambda h: math.dist(h, e))
        legs.append(LineString([(foot[0] - 0.5 * n[0], foot[1] - 0.5 * n[1]),
                                (end[0] + 0.5 * n[0], end[1] + 0.5 * n[1])]))
        if abs(t - ta) <= abs(t - tb):  # the line ends just past the foot on this side
            ta = t - 0.5 if ta < tb else t + 0.5
        else:
            tb = t + 0.5 if tb > ta else t - 0.5
    if not legs:
        return chords
    return [LineString([(p[0] + ta * d[0], p[1] + ta * d[1]), (p[0] + tb * d[0], p[1] + tb * d[1])]), *legs]


def _one_wall(chords: list[LineString]) -> list[LineString]:
    """Parallel step chords of one section border that continue each other (overlapping by less than
    ``ALIGN_FT`` along their direction) less than ``ALIGN_FT`` apart are one wall: they take their length-weighted
    mean position (no jog of a foot or two where two plane pairs' lines meet)."""
    if not chords:
        return chords
    group = list(range(len(chords)))

    def find(k: int) -> int:
        while group[k] != k:
            k = group[k]
        return k

    info = []
    for c in chords:
        (x0, y0), (x1, y1) = c.coords[0], c.coords[-1]
        ln = max(math.hypot(x1 - x0, y1 - y0), 1e-9)
        info.append(((x1 - x0) / ln, (y1 - y0) / ln, x0, y0, ln))
    for a in range(len(chords)):
        for b in range(a + 1, len(chords)):
            da, db = info[a], info[b]
            if ang_diff(_deg(da[:2]), _deg(db[:2])) > 1.0:
                continue
            dx, dy = da[0], da[1]
            off = -dy * (db[2] - da[2]) + dx * (db[3] - da[3])
            ta = sorted((0.0, da[4]))
            tb = sorted(((db[2] - da[2]) * dx + (db[3] - da[3]) * dy,
                         (chords[b].coords[-1][0] - da[2]) * dx + (chords[b].coords[-1][1] - da[3]) * dy))
            overlap = min(ta[1], tb[1]) - max(ta[0], tb[0])
            if 1e-6 < abs(off) <= ALIGN_FT and overlap < ALIGN_FT:
                group[find(b)] = find(a)
    out = list(chords)
    for root in {find(k) for k in range(len(chords))}:
        ks = [k for k in range(len(chords)) if find(k) == root]
        if len(ks) < 2:
            continue
        r = info[root]
        offs = [(-r[1] * (info[k][2] - r[2]) + r[0] * (info[k][3] - r[3]), info[k][4]) for k in ks]
        mean = sum(o * w for o, w in offs) / sum(w for _, w in offs)
        for k, (o, _) in zip(ks, offs, strict=True):
            m = mean - o
            out[k] = LineString([(x - r[1] * m, y + r[0] * m) for x, y in chords[k].coords])
    return out
