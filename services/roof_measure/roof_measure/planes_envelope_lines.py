"""Roof lines of a section for ``planes_envelope`` (internal): which planes form a section, where sections meet (straight
wall steps), and the line between two planes of a section (where their heights agree, a straight step, or a split
between two clusters of one face) with the side of it each plane must stay on.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .planes_envelope_cells import MEET_FT, NEAR_FT
from .planes_envelope_geom import (
    Eq,
    anchor_between,
    ang_diff,
    l_segments,
    long_line,
    meet_line,
    merge_lines,
    sample_line,
    step_path,
    z_at,
)
from .planes_envelope_measure import (
    _align,
    _offset,
    _ordered,
    _shifted,
    _step_onto_meet,
    touch_points,
)

ADJACENT_FT = 2.0  # planes sharing a border longer than this are neighbours
MIN_GRAD_DIFF = 0.05  # planes whose gradients differ by less than this are parallel (no intersection line)
LINE_NEAR_FT = 6.0  # an intersection line is used only when it passes this near where the two clusters meet
FAR = 400.0
SIDE_SHARE = 0.8  # an intersection line is the border when this share of each cluster lies on its own side
OPPOSITE_DEG = 90.0  # planes whose facings differ by this much (ridge, valley, hip) ...
OPPOSITE_SHARE = 0.6  # ... need only this share (the clusters of a ridge often overlap it a little)
LOCAL_FT = 4.0  # which side of a line two clusters are on is judged where both are within this distance
HUG_FT = 1.5  # a box side this near the outline along its whole length is the outline
MEET_PLAN_FT = 3.0  # ... or when the border is this near (in plan) to where their heights agree
CONSTRAIN_SHARE = 0.6  # a plane must stay on its cluster's side of a line that separates at least this share
STEP_MIN_FT = 4.0
FLAT_SLOPE = 0.03  # a plane with less slope than this (about 3/8 in 12) is flat
MIN_TOUCH_PTS = 8  # ... when they do so over at least this many 0.5 ft samples (about 2 ft of border)
SHIFT_MIN_FT = 1.0  # an intersection line further than this from the measured border moves onto it ...
MAX_SHIFT_FT = 3.0  # ... by at most this much (further off, the measurement is not of this line)


def _shared_line(a: BaseGeometry, b: BaseGeometry) -> BaseGeometry:
    return merge_lines(a.boundary.intersection(b.boundary))


def _median_gap(e1: Eq, e2: Eq, line: BaseGeometry) -> float:
    pts = sample_line(line)
    if not pts:
        return math.inf
    gaps = sorted(abs(z_at(e1, x, y) - z_at(e2, x, y)) for x, y in pts)
    return gaps[len(gaps) // 2]


def _meet(e1: Eq, e2: Eq, line: BaseGeometry) -> bool:
    """True when two planes meet along their (current, approximate) border: the median height gap there is at most
    ``MEET_FT``, or the plan distance from the border to where they would meet (gap over the difference of their
    slopes) is at most ``MEET_PLAN_FT`` (steep planes: a border placed a foot off already shows a big gap)."""
    gap = _median_gap(e1, e2, line)
    if gap <= MEET_FT:
        return True
    g = math.hypot(e1[0] - e2[0], e1[1] - e2[1])
    return g >= MIN_GRAD_DIFF and gap / g <= MEET_PLAN_FT


def _flat(eq: Eq) -> bool:
    return math.hypot(eq[0], eq[1]) < FLAT_SLOPE


def neighbours(shapes: list[BaseGeometry]) -> dict[tuple[int, int], BaseGeometry]:
    """Pairs of planes sharing a border longer than ``ADJACENT_FT``, with that border."""
    shared: dict[tuple[int, int], BaseGeometry] = {}
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            line = _shared_line(shapes[i], shapes[j])
            if not line.is_empty and line.length > ADJACENT_FT:
                shared[(i, j)] = line
    return shared


def sections(shared: dict[tuple[int, int], BaseGeometry], eqs: list[Eq], raws: list[BaseGeometry],
             shapes: list[BaseGeometry], dirs: list[float]) -> list[int]:
    """Section number per plane: connected components of neighbours that meet along their current border
    (``_meet``) or whose intersection line cleanly separates their clusters right where they meet."""
    n = len(eqs)
    clean = set()
    for (i, j) in shared:
        ri = raws[i] if not raws[i].is_empty else shapes[i]
        rj = raws[j] if not raws[j].is_empty else shapes[j]
        anchor = anchor_between(ri, rj)
        ml = meet_line(eqs[i], eqs[j], anchor, dirs, MIN_GRAD_DIFF)
        if ml is not None and math.dist(anchor, ml[0]) <= MEET_PLAN_FT and _sides_of(_half(*ml), ri, rj, anchor)[1] >= SIDE_SHARE:
            clean.add((i, j))
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for (i, j), line in shared.items():
        if _flat(eqs[i]) != _flat(eqs[j]):  # a flat roof and a pitched one are different sections (a step between)
            continue
        if _meet(eqs[i], eqs[j], line) or (i, j) in clean:
            parent[find(i)] = find(j)
    roots = sorted({find(i) for i in range(n)})
    return [roots.index(find(i)) for i in range(n)]


def _half(p: tuple[float, float], d: tuple[float, float]) -> Polygon:
    """The half-plane left of the line through p with direction d (a big polygon)."""
    far = FAR
    a = (p[0] - far * d[0], p[1] - far * d[1])
    b = (p[0] + far * d[0], p[1] + far * d[1])
    n = (-d[1] * far, d[0] * far)
    return Polygon([a, b, (b[0] + n[0], b[1] + n[1]), (a[0] + n[0], a[1] + n[1])])


def _sides_of(h: Polygon, ri: BaseGeometry, rj: BaseGeometry, anchor: tuple[float, float]) -> tuple[int, float]:
    """Which side of a line (``h`` = its left half-plane) the two clusters are on WHERE THEY FACE EACH OTHER (both
    clipped to the band within ``LOCAL_FT`` of both; a big L-shaped plane lies on both sides of its valley line
    beyond the valley's end): (+1 when
    ``ri`` is left and ``rj`` right, -1 for the reverse, 0 when neither) and the smaller of the two own-side shares."""
    zone = ri.buffer(LOCAL_FT).intersection(rj.buffer(LOCAL_FT))  # the band where the two clusters face each other
    if zone.is_empty or zone.area <= 0:
        zone = Point(anchor).buffer(2.5 * LOCAL_FT)
    ri, rj = ri.intersection(zone), rj.intersection(zone)
    if ri.is_empty or rj.is_empty or ri.area <= 0 or rj.area <= 0:
        return 0, 0.0
    si, sj = ri.intersection(h).area / ri.area, rj.intersection(h).area / rj.area
    if si >= sj:
        return 1, min(si, 1.0 - sj)
    return -1, min(1.0 - si, sj)


def _facing_gap(e1: Eq, e2: Eq) -> float:
    """Angle (degrees) between two planes' facings; 180 for a flat plane next to a sloped one."""
    g1, g2 = math.hypot(e1[0], e1[1]), math.hypot(e2[0], e2[1])
    if g1 < 1e-6 or g2 < 1e-6:
        return 180.0
    c = (e1[0] * e2[0] + e1[1] * e2[1]) / (g1 * g2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _split_line(ri: BaseGeometry, rj: BaseGeometry, u: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Between two clusters of one roof face (parallel planes): the building axis most across the line joining their
    centroids, through the middle of the gap between them."""
    from shapely.ops import nearest_points

    p1, p2 = nearest_points(ri, rj)
    ci, cj = ri.centroid, rj.centroid
    v = math.degrees(math.atan2(cj.y - ci.y, cj.x - ci.x)) % 180.0
    deg = max((u % 180.0, (u + 90.0) % 180.0), key=lambda a: ang_diff(v, a))
    r = math.radians(deg)
    return ((p1.x + p2.x) / 2, (p1.y + p2.y) / 2), (math.cos(r), math.sin(r))


def _pair_lines(i: int, j: int, ri: BaseGeometry, rj: BaseGeometry, eqs: list[Eq], line: BaseGeometry | None,
                dirs: list[float], u: float) -> tuple[str, list[tuple[tuple[float, float], tuple[float, float]]]]:
    """The roof line(s) between two planes of a section and what they are: ``meet`` (where the planes have the same
    height and the line separates their clusters), ``step`` (a fitted axis line along their current border),
    ``split`` (parallel planes: an axis line through the gap) or ``none``."""
    adjacent = line is not None
    anchor = anchor_between(ri, rj)
    ml = meet_line(eqs[i], eqs[j], anchor, dirs, MIN_GRAD_DIFF)
    level = not adjacent or _meet(eqs[i], eqs[j], line)
    if ml is not None and math.dist(anchor, ml[0]) <= LINE_NEAR_FT:
        sep, share = _sides_of(_half(*ml), ri, rj, anchor)
        opposite = _facing_gap(eqs[i], eqs[j]) >= OPPOSITE_DEG
        # a line that cleanly separates the clusters right where they meet is their border even when the current
        # (gap-filled) border is too far off for the height test; a weaker separation also needs the height test
        if sep and (share >= SIDE_SHARE or (level and opposite and share >= OPPOSITE_SHARE)):
            return "meet", [ml]
    if adjacent and line.length >= STEP_MIN_FT and not level:
        pts = sample_line(line)
        return "step", step_path(pts, u)
    if ((ml is None or not level or _facing_gap(eqs[i], eqs[j]) < OPPOSITE_DEG)
            and ri.distance(rj) <= NEAR_FT and not ri.is_empty and not rj.is_empty):
        return "split", [_split_line(ri, rj, u)]
    if adjacent and line.length >= STEP_MIN_FT:
        pts = sample_line(line)
        return "step", step_path(pts, u)
    return "none", []


def _faces(members: list[int], eqs: list[Eq]) -> list[list[int]]:
    """Planes that share one equation (one face split by an obstacle) as groups, in member order."""
    groups: dict[Eq, list[int]] = {}
    for k in members:
        groups.setdefault(tuple(eqs[k]), []).append(k)  # type: ignore[arg-type]
    return list(groups.values())


def _union(ks: list[int], raws: list[BaseGeometry], shapes: list[BaseGeometry]) -> BaseGeometry:
    parts = [raws[k] if not raws[k].is_empty else shapes[k] for k in ks]
    return parts[0] if len(parts) == 1 else unary_union(parts)


def section_chords(members: list[int], raws: list[BaseGeometry], shapes: list[BaseGeometry], eqs: list[Eq],
                   shared: dict[tuple[int, int], BaseGeometry], dirs: list[float], u: float,
                   sides: dict[int, list[tuple[Polygon, BaseGeometry]]], log_to: list[dict[str, Any]],
                   outline: BaseGeometry) -> list[LineString]:
    """The roof lines of a section. Planes of one face are handled as one. Each line's DIRECTION comes from the
    plane equations, its POSITION from the measured border where the two clusters touch (within ``TOUCH_FT``) when
    that disagrees by more than ``SHIFT_MIN_FT`` (at 2-5/12 a 0.3 ft height error moves an intersection 1-2 ft);
    step lines are fitted to the measured border when there is one. ``sides[k]`` collects (half-plane, zone): within
    the zone (near both clusters) plane k must stay on its cluster's side of a line that separates its cluster from
    a neighbour's. Step lines run to ``outline`` (the section region's boundary)."""
    faces = _faces(members, eqs)
    recs: list[dict[str, Any]] = []
    for x, fa in enumerate(faces):
        for fb in faces[x + 1:]:
            ri, rj = _union(fa, raws, shapes), _union(fb, raws, shapes)
            borders = [shared[(min(i, j), max(i, j))] for i in fa for j in fb if (min(i, j), max(i, j)) in shared]
            line = merge_lines(unary_union(borders)) if borders else None
            if line is None and ri.distance(rj) > NEAR_FT:
                continue
            kind, lines = _pair_lines(fa[0], fb[0], ri, rj, eqs, line, dirs, u)
            if not lines:
                continue
            touch = touch_points(ri, rj)
            rec = {"fa": fa, "fb": fb, "ri": ri, "rj": rj, "kind": kind, "lines": lines, "line": line, "touch": touch,
                   "computed": lines, "measured_shift_ft": None}
            if len(touch) >= MIN_TOUCH_PTS and kind == "meet":
                offs = sorted(_offset(p, lines[0]) for p in touch)
                m = offs[len(offs) // 2]
                rec["measured_shift_ft"] = round(m, 2)
                if SHIFT_MIN_FT < abs(m) <= MAX_SHIFT_FT:
                    rec["lines"] = [_shifted(lines[0], m)]
            elif len(touch) >= MIN_TOUCH_PTS and kind == "step":
                rec["lines"] = step_path(_ordered(touch), u)
                rec["measured_shift_ft"] = "fitted"
            recs.append(rec)
    _align(recs, eqs)
    _step_onto_meet(recs)
    chords: list[LineString] = []
    for rec in recs:
        lines, line, ri, rj = rec["lines"], rec["line"], rec["ri"], rec["rj"]
        if rec["kind"] == "step" and line is not None:
            chords += l_segments(lines, sample_line(line), outline)
        else:
            chords.append(long_line(*lines[0]))
        sep = 0
        if len(lines) == 1:
            h = _half(*lines[0])
            sep, share = _sides_of(h, ri, rj, anchor_between(ri, rj))
            if sep and share >= CONSTRAIN_SHARE:
                rest = _half(lines[0][0], (-lines[0][1][0], -lines[0][1][1]))
                zone = ri.buffer(NEAR_FT).intersection(rj.buffer(NEAR_FT))  # the line only binds near both
                for i in rec["fa"]:
                    sides.setdefault(i, []).append((h if sep > 0 else rest, zone))
                for j in rec["fb"]:
                    sides.setdefault(j, []).append((rest if sep > 0 else h, zone))
            else:
                sep = 0
        log_to.append({"a": rec["fa"][0], "b": rec["fb"][0], "faces": (rec["fa"], rec["fb"]), "kind": rec["kind"],
                       "lines": lines, "computed": rec["computed"], "measured_shift_ft": rec["measured_shift_ft"],
                       "aligned": rec.get("aligned", False), "touch_pts": len(rec["touch"]), "separates": bool(sep)})
    return chords


def box_sides(raw: BaseGeometry, u: float, fp: Polygon) -> list[LineString]:
    """The sides of the cluster's bounding box in the building axes, each run 2 ft past its corners; a side that hugs
    the outline (every point within ``HUG_FT``) is left out (the outline is that side, and a box side a foot inside
    it would cut a wedge)."""
    from shapely import affinity

    turned = affinity.rotate(raw, -u, origin=(0.0, 0.0))
    x0, y0, x1, y1 = turned.bounds
    ring = list(affinity.rotate(Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)]), u, origin=(0.0, 0.0)).exterior.coords)
    out = []
    for a, b in itertools.pairwise(ring):
        side = LineString([a, b])
        if all(fp.exterior.distance(side.interpolate(t, normalized=True)) <= HUG_FT for t in (0.0, 0.25, 0.5, 0.75, 1.0)):
            continue
        ln = max(side.length, 1e-9)
        d = ((b[0] - a[0]) / ln, (b[1] - a[1]) / ln)
        out.append(LineString([(a[0] - 2.0 * d[0], a[1] - 2.0 * d[1]), (b[0] + 2.0 * d[0], b[1] + 2.0 * d[1])]))
    return out
