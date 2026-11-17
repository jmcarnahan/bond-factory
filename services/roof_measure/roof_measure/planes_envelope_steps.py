"""Wall steps between roof sections for ``planes_envelope`` (internal): a step is a wall, and walls are built square.

``section_regions`` cuts the outline into one region per section along straight step lines. Each step's DIRECTION:
the building axis when the border runs within 25 degrees of one (as before); otherwise the level line (contour) of
a square pitched plane of the pair whose slope runs across the border (its eave or top edge is the wall line);
otherwise the measured border's own direction only when the raw clusters clearly run side by side diagonally over
``DIAGONAL_MIN_FT`` (a real angled wing, whose planes do not face the building axes); otherwise an L of two axis
segments. When one step path between two multi-plane
sections leaves the border's points more than ``PER_PAIR_FT`` away (a flat roof ringed by slopes: the step turns several
corners), every pair of neighbouring planes across the two sections gets its own step line instead.

``onto_walls`` puts a step line that runs a few inches beside a parallel outline wall it starts from onto that wall
(the wall continues; a line 0.02 ft off it leaves a sliver that cleanup can only tear).
"""

from __future__ import annotations

import itertools
import math

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .planes_envelope_cells import cut
from .planes_envelope_geom import (
    END_SLACK_FT,
    STEP_SNAP_DEG,
    Eq,
    _axis_fit,
    ang_diff,
    l_segments,
    sample_line,
    step_path,
)
from .planes_envelope_lines import ADJACENT_FT, _shared_line, box_sides
from .planes_envelope_measure import _ordered, touch_points
from .planes_envelope_walls import _legs, _one_wall, onto_walls

Pt = tuple[float, float]
Line = tuple[Pt, Pt]

DIAGONAL_MIN_FT = 8.0  # a step stays off the axes only when the clusters run side by side diagonally this far ...
DIAGONAL_FIT_FT = 0.75  # ... along a line that fits them within this
MIN_TOUCH = 8  # touch points (0.5 ft samples) needed before the measured border is used
CONTOUR_SHARE = 0.7  # a plane whose slope across the border is at least this share of its slope has it as eave/top
FLAT = 0.03
PER_PAIR_FT = 4.0  # one step path this far from its border's points gives way to a line per plane pair
AWNING_SQFT = 80.0  # a one-plane section with a smaller cluster (an awning, a bay) is the box of its cluster


def _deg(d: Pt) -> float:
    return math.degrees(math.atan2(d[1], d[0])) % 180.0


def _on_axis(lines: list[Line], u: float) -> bool:
    return all(min(ang_diff(_deg(d), u), ang_diff(_deg(d), u + 90.0)) < 1e-6 for _, d in lines)


def _pca(pts: list[Pt]) -> tuple[float, float]:
    """Direction (degrees mod 180) of the points' main axis and their rms distance from that line."""
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    t = 0.5 * math.atan2(2 * sxy, sxx - syy)
    d = (math.cos(t), math.sin(t))
    rms = math.sqrt(sum((-d[1] * (p[0] - mx) + d[0] * (p[1] - my)) ** 2 for p in pts) / len(pts))
    return math.degrees(t) % 180.0, rms


def _forced_l(pts: list[Pt], u: float) -> list[Line]:
    """The best path of two axis segments through the ordered points (one axis line when that is as good)."""
    axes = (u % 180.0, (u + 90.0) % 180.0)
    best: tuple[float, list[Line]] | None = None
    for a in axes:
        p, d, w = _axis_fit(pts, a)
        if best is None or w < best[0]:
            best = (w, [(p, d)])
    for k in range(3, len(pts) - 2):
        for a1, a2 in ((axes[0], axes[1]), (axes[1], axes[0])):
            p1, d1, w1 = _axis_fit(pts[:k], a1)
            p2, d2, w2 = _axis_fit(pts[k:], a2)
            if best is None or max(w1, w2) < best[0] - 1e-9:
                best = (max(w1, w2), [(p1, d1), (p2, d2)])
    return best[1] if best is not None else []


def _contours(eqs: list[Eq], deg: float, u: float) -> set[float]:
    """Axis directions that are the level line of a pitched plane whose slope runs across a border of direction
    ``deg`` (its eave or top edge lies along the border, so the wall does)."""
    out = set()
    r = math.radians(deg)
    n = (-math.sin(r), math.cos(r))
    for a, b, _ in eqs:
        g = math.hypot(a, b)
        if g < FLAT or abs(a * n[0] + b * n[1]) < CONTOUR_SHARE * g:
            continue
        c = math.degrees(math.atan2(a, -b)) % 180.0  # the level line is perpendicular to the gradient
        for ax in (u % 180.0, (u + 90.0) % 180.0):
            if ang_diff(c, ax) < 1.0:
                out.add(ax)
    return out


def step_lines(pts: list[Pt], touch: list[Pt], u: float, eqs: list[Eq]) -> list[Line]:
    """The step's line(s), (point, unit direction), from the gap-filled border ``pts`` (ordered), the measured
    border ``touch`` and the planes on its two sides (see the module docstring)."""
    lines = step_path(pts, u)
    if not lines or _on_axis(lines, u):
        return lines
    meas = _ordered(touch) if len(touch) >= MIN_TOUCH else []
    use = meas or pts
    deg, rms = _pca(use)
    con = _contours(eqs, deg, u)
    if len(con) == 1:  # a square plane's eave or top edge: the wall runs along it, where it was measured
        p, d, _ = _axis_fit(use, con.pop())
        return [(p, d)]
    if (meas and math.dist(meas[0], meas[-1]) >= DIAGONAL_MIN_FT and rms <= DIAGONAL_FIT_FT
            and min(ang_diff(deg, u), ang_diff(deg, u + 90.0)) > STEP_SNAP_DEG):
        p, d, _ = _axis_fit(meas, deg)  # the clusters run side by side diagonally: a real angled wall
        return [(p, d)]
    return _forced_l(pts, u)


def _worst(pts: list[Pt], chords: list[LineString]) -> float:
    """How far the border's points (its first and last ``END_SLACK_FT`` aside) lie from the step chords."""
    if not chords or len(pts) < 2:
        return math.inf
    run = [0.0]
    for a, b in itertools.pairwise(pts):
        run.append(run[-1] + math.dist(a, b))
    total = run[-1]
    keep = [q for q, s in zip(pts, run, strict=True) if END_SLACK_FT <= s <= total - END_SLACK_FT] or pts
    both = unary_union(chords)
    return max(both.distance(Point(q)) for q in keep)


def _pair_chords(line: BaseGeometry, ra: BaseGeometry, rb: BaseGeometry, u: float, eqs: list[Eq],
                 fp: Polygon, boxed: bool = False) -> tuple[list[LineString], bool] | None:
    """The step chords for one border between two sections (or two planes of different sections) and whether they
    were redrawn from a diagonal (True); None for a diagonal border next to a ``boxed`` section (an awning: its box
    is its border)."""
    pts = sample_line(line)
    if len(pts) < 2:
        return [], False
    lines = step_path(pts, u)
    if not lines or _on_axis(lines, u):  # the border runs along an axis (or is one L): as it always was
        return l_segments(onto_walls(lines, pts, fp.exterior), pts, fp.boundary), False
    if boxed:
        return None
    touch = touch_points(ra, rb) if not ra.is_empty and not rb.is_empty else []
    return _legs(onto_walls(step_lines(pts, touch, u, eqs), pts, fp.exterior), pts, fp, touch), True


def section_regions(fp: Polygon, shapes: list[BaseGeometry], raws: list[BaseGeometry], sec: list[int],
                    u: float, eqs: list[Eq] | None = None, legacy: bool = False) -> list[BaseGeometry]:
    """Each section's region: the outline cut by straight step lines between sections (an island section, one that
    does not reach the outline such as a dormer, by the axis box of its clusters), cells by largest overlap.
    ``legacy`` draws every step as one fitted line or L, diagonal when the border is (the 0.4.0 round-2 rule)."""
    ns = max(sec) + 1
    unions = [unary_union([s for s, k in zip(shapes, sec, strict=True) if k == q]) for q in range(ns)]
    if ns == 1:
        return [fp]
    eqs = eqs if eqs is not None else [(0.0, 0.0, 0.0)] * len(shapes)
    seen = [unary_union([r for r, k in zip(raws, sec, strict=True) if k == q and not r.is_empty]) for q in range(ns)]
    island = [unions[q].boundary.intersection(fp.exterior.buffer(0.05)).length < 1.0 for q in range(ns)]
    small = [not island[q] and sec.count(q) == 1 and 0 < seen[q].area < AWNING_SQFT for q in range(ns)]
    chords: list[LineString] = []
    for q in range(ns):
        if island[q]:
            chords += box_sides(seen[q] if not seen[q].is_empty else unions[q], u, fp)
    boxed: set[int] = set()
    for a in range(ns):
        for b in range(a + 1, ns):
            if island[a] or island[b]:
                continue
            line = _shared_line(unions[a], unions[b])
            if line.is_empty or line.length <= ADJACENT_FT:
                continue
            ia = [k for k in range(len(sec)) if sec[k] == a]
            ib = [k for k in range(len(sec)) if sec[k] == b]
            if legacy:
                pts = sample_line(line)
                chords += l_segments(step_path(pts, u), pts, fp.boundary)
                continue
            got = _pair_chords(line, seen[a], seen[b], u, [eqs[k] for k in ia + ib], fp, small[a] or small[b])
            if got is None:  # a diagonal border of an awning: its box is the border (below)
                boxed |= {q for q in (a, b) if small[q]}
                continue
            pair = got[0]
            if len(ia) + len(ib) > 2 and _worst(sample_line(line), pair) > PER_PAIR_FT:
                # one path cannot follow this border: a step line per pair of neighbouring planes across it
                per: list[LineString] = []
                for i in ia:
                    for j in ib:
                        pl = _shared_line(shapes[i], shapes[j])
                        if not pl.is_empty and pl.length > ADJACENT_FT:
                            per += (_pair_chords(pl, raws[i], raws[j], u, [eqs[i], eqs[j]], fp) or ([], False))[0]
                pair = _one_wall(per) or pair
            chords += pair
    for q in sorted(boxed):
        chords += box_sides(seen[q], u, fp)
        unions[q] = unions[q].union(seen[q].envelope)
    for _ in range(2):  # a second pass boxes a section the step lines did not isolate (an awning on a flat roof)
        cells = cut(fp, chords)
        owner = [max(range(ns), key=lambda q: (c.intersection(unions[q]).area, -q)) for c in cells]
        regions = [unary_union([c for c, o in zip(cells, owner, strict=True) if o == q]) for q in range(ns)]
        lost = [q for q in range(ns) if not seen[q].is_empty and regions[q].area < 0.4 * seen[q].area]
        if not lost:
            break
        chords = chords + [side for q in lost for side in box_sides(seen[q], u, fp)]
        unions = [u_q.union(seen[q].envelope) if q in lost else u_q for q, u_q in enumerate(unions)]
    return regions
