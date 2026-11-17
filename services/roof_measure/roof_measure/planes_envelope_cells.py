"""Cells of a roof section and who owns them, plus the classified shared borders (internal, for ``planes_envelope``).

A section's region is cut by its roof lines into cells (``cut``); each cell goes to one plane (``label_envelope`` /
``label_arrangement``); small or detached pieces join a neighbour (``tidy_labels``); ``borders`` classifies every edge
two finished planes share.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .classify import polygons_of
from .planes_envelope_geom import Eq, merge_lines, sample_line, straight_runs, z_at

Sides = dict[int, list[tuple[Polygon, BaseGeometry]]]  # per plane: (half-plane it must stay in, zone where that binds)

COVERED_SHARE = 0.6  # a cell this much covered by raw clusters goes to the plane whose cluster covers most of it
NEAR_FT = 6.0  # a plane is a candidate for a cell only when its raw cluster lies within this distance
MIN_CELL_SQFT = 6.0  # smaller cells join the neighbour they share the longest edge with
THIN_FT = 3.0  # a cell on the outline narrower than this, its own cluster thin there, joins the plane across its long side
SLIVER_FT = 0.5  # ... as do slivers: cells whose mean width (2 x area / perimeter) is under this
MEET_FT = 1.5  # two planes meet along a border when their median height gap there is under this
SEAM_COS = math.cos(math.radians(10.0))  # planes facing within 10 degrees of each other meet in a seam, not a roof line
# (a wing bent 20 degrees off its neighbour meets it in a real hip and valley; measured seams face 0-1.4 degrees apart)
LEVEL_FT = 0.25  # a line whose ends differ in height by at most this, or by LEVEL_SHARE of its plan length, is level
LEVEL_SHARE = 0.05  # (relative: a level ridge drawn a few degrees off by the turn onto a diagonal stays a ridge)
ACROSS_SHARE = 0.05  # two planes that both run along a line: a slope across it of this share of their slope decides
FLAT_SLOPE = 0.03  # less slope than this is a flat roof; a flat roof meeting a pitched one is a step
MEASURED_MEET_FT = 2.0  # planes this close in height where LiDAR saw them side by side meet (not a wall step)
ALONG_SHARE = 0.25  # a plane whose slope across a line is under this share of its slope runs along the line  # a ridge's height changes by less than this along it (else it is a hip)


def cut(region: BaseGeometry, chords: list[LineString]) -> list[Polygon]:
    """The cells of ``region`` between its outline and the chords (lines cut to the region)."""
    lines = [region.boundary]
    wide = region.buffer(2.0)  # cut a little beyond the outline so every chord crosses it (no dangling end)
    for c in chords:
        part = c.intersection(wide)
        if not part.is_empty:
            lines.append(part)
    cells = []
    for g in polygonize(unary_union(lines)):
        if g.area > 1e-6 and region.contains(g.representative_point()):
            cells.append(g)
    return cells


def _cover(cell: Polygon, members: list[int], raws: list[BaseGeometry]) -> dict[int, float]:
    return {k: float(cell.intersection(raws[k]).area) for k in members if not raws[k].is_empty}


def _fits(cell: Polygon, k: int, sides: Sides) -> bool:
    """True when the cell lies on plane k's own side of every line that separates k's cluster from a neighbour's."""
    rp = cell.representative_point()
    return all(h.contains(rp) for h, zone in sides.get(k, []) if zone.contains(rp))


def _lowest(cell: Polygon, members: list[int], raws: list[BaseGeometry], eqs: list[Eq], shapes: list[BaseGeometry],
            sides: Sides) -> int:
    """The lowest plane at the cell among the nearby planes whose side constraints the cell satisfies."""
    rp = cell.representative_point()
    near = [k for k in members if (raws[k] if not raws[k].is_empty else shapes[k]).distance(rp) <= NEAR_FT]
    near = near or [min(members, key=lambda k: ((raws[k] if not raws[k].is_empty else shapes[k]).distance(rp), k))]
    fits = [k for k in near if _fits(cell, k, sides)]
    if fits:
        return min(fits, key=lambda k: (z_at(eqs[k], rp.x, rp.y), k))
    # no nearby plane may be here (two of its lines disagree): the fewest broken lines, then the nearest cluster
    return min(near, key=lambda k: (_broken(rp, k, sides), (raws[k] if not raws[k].is_empty else shapes[k]).distance(rp), k))


def _broken(rp: Point, k: int, sides: Sides) -> int:
    return sum(1 for h, zone in sides.get(k, []) if zone.contains(rp) and not h.contains(rp))


def label_envelope(cells: list[Polygon], members: list[int], raws: list[BaseGeometry], eqs: list[Eq],
                   shapes: list[BaseGeometry], sides: Sides | None = None) -> tuple[list[int], float]:
    """Rule (a) for cells well covered by clusters of planes that may be there (on their own side of their roof
    lines), else the lowest such nearby plane (b). Also returns the share of the raw-covered area where the clusters
    disagree with (b)."""
    sides = sides or {}
    out, bad, tot = [], 0.0, 0.0
    for cell in cells:
        cov = _cover(cell, members, raws)
        covered = sum(cov.values())
        low = _lowest(cell, members, raws, eqs, shapes, sides)
        ok = {k: v for k, v in cov.items() if v > 0 and _fits(cell, k, sides)}
        top = max(ok, key=lambda k: (ok[k], -k)) if ok else None
        out.append(top if top is not None and sum(ok.values()) > COVERED_SHARE * cell.area else low)
        tot += covered
        bad += sum(v for k, v in cov.items() if k != low)
    return out, (bad / tot if tot > 0 else 0.0)


def label_arrangement(cells: list[Polygon], members: list[int], raws: list[BaseGeometry],
                      shapes: list[BaseGeometry], sides: Sides | None = None) -> list[int]:
    """Rule (a) only: the plane whose raw cluster covers most of the cell (planes on their own side of their roof
    lines first); a cell no cluster touches goes to the plane whose gap-filled polygon (the input tiling) covers most
    of it."""
    sides = sides or {}
    out = []
    for cell in cells:
        cov = _cover(cell, members, raws)
        ok = {k: v for k, v in cov.items() if _fits(cell, k, sides)}
        pick = ok if sum(ok.values()) > 0.05 * cell.area else cov
        if sum(pick.values()) > 0.05 * cell.area:
            out.append(max(pick, key=lambda k: (pick[k], -k)))
        else:
            out.append(max(members, key=lambda k: (cell.intersection(shapes[k]).area, -k)))
    return out


def _shared(a: BaseGeometry, b: BaseGeometry) -> float:
    return float(a.boundary.intersection(b.boundary).length)


def _adjacency(cells: list[Polygon]) -> list[dict[int, float]]:
    """Per cell: the cells it shares an edge with and the shared length."""
    adj: list[dict[int, float]] = [{} for _ in cells]
    for i, a in enumerate(cells):
        for j in range(i + 1, len(cells)):
            if a.distance(cells[j]) > 1e-6:
                continue
            ln = _shared(a, cells[j])
            if ln > 1e-6:
                adj[i][j] = adj[j][i] = ln
    return adj


def _border_len(i: int, lab: int, labels: list[int], adj: list[dict[int, float]]) -> float:
    return sum(ln for j, ln in adj[i].items() if labels[j] != lab)


def _short_side(c: Polygon) -> float:
    r = list(c.minimum_rotated_rectangle.exterior.coords)
    return min(math.dist(r[0], r[1]), math.dist(r[1], r[2])) if len(r) >= 3 else 0.0


def tidy_labels(cells: list[Polygon], labels: list[int], raws: list[BaseGeometry], sides: Sides | None = None,
                outline: BaseGeometry | None = None) -> list[int]:
    """Clean the labelling: (1) a cell whose own plane's cluster covers less than ``COVERED_SHARE`` of it moves to the
    neighbouring plane that shortens the borders most (when that plane may be there): this removes the jogs that
    roof lines extended across other planes leave; (2) cells under ``MIN_CELL_SQFT`` and (3) pieces of a plane
    detached from its main part (the part holding most of its raw cluster) join the neighbouring plane they share the
    longest edge with (slivers too: mean width under ``SLIVER_FT``)."""
    labels = list(labels)
    sides = sides or {}
    adj = _adjacency(cells)
    own = [cells[i].intersection(raws[labels[i]]).area / cells[i].area if not raws[labels[i]].is_empty else 0.0
           for i in range(len(cells))]
    for _ in range(4):
        moved = False
        for i in sorted(range(len(cells)), key=lambda i: cells[i].area):
            if own[i] >= COVERED_SHARE and cells[i].area >= MIN_CELL_SQFT:
                continue
            here = _border_len(i, labels[i], labels, adj)
            cover = {lab: cells[i].intersection(raws[lab]).area / cells[i].area if not raws[lab].is_empty else 0.0
                     for lab in {labels[j] for j in adj[i]} - {labels[i]}}
            best = min((lab for lab, cv in cover.items() if cv >= own[i] - 0.05),  # never against the cell's evidence
                       key=lambda lab: (_border_len(i, lab, labels, adj), lab), default=None)
            if best is None or not _fits(cells[i], best, sides):
                continue
            if _border_len(i, best, labels, adj) < here - 0.5:
                labels[i] = best
                own[i] = cells[i].intersection(raws[best]).area / cells[i].area if not raws[best].is_empty else 0.0
                moved = True
        if not moved:
            break
    if outline is not None:  # a thin strip between a roof line and the outline goes across that line
        for i in sorted(range(len(cells)), key=lambda i: cells[i].area):
            c = cells[i]
            if own[i] >= COVERED_SHARE or c.boundary.intersection(outline.buffer(0.05)).length < 1.0 or _short_side(c) >= THIN_FT:
                continue
            nb = max((j for j in adj[i] if labels[j] != labels[i]), key=lambda j: (adj[i][j], -j), default=None)
            if nb is not None and adj[i][nb] >= 0.5 * max(adj[i].values()):
                labels[i] = labels[nb]
    for _ in range(3):
        for i, c in enumerate(cells):
            if c.area < MIN_CELL_SQFT or 2.0 * c.area / c.length < SLIVER_FT:
                nb = max(adj[i], key=lambda j: (adj[i][j], -j), default=None)  # the longest edge, whatever its label
                if nb is not None:
                    labels[i] = labels[nb]
        changed = False
        for k in sorted(set(labels)):
            idx = [i for i, lab in enumerate(labels) if lab == k]
            parts = polygons_of(unary_union([cells[i] for i in idx]))
            if len(parts) < 2:
                continue
            main = max(parts, key=lambda p: (p.intersection(raws[k]).area if not raws[k].is_empty else 0.0, p.area))
            for i in idx:
                if main.contains(cells[i].representative_point()):
                    continue
                others = [j for j in range(len(cells)) if labels[j] != k]
                part = next(p for p in parts if p.contains(cells[i].representative_point()))
                nb = max(others, key=lambda j: (_shared(part, cells[j]), -j), default=None)
                if nb is not None and _shared(part, cells[nb]) > 0:
                    labels[i] = labels[nb]
                    changed = True
        if not changed:
            break
    return labels


def _side(shape: BaseGeometry, m: Point, n: tuple[float, float]) -> float:
    """+1 when the plane lies on the +n side of the border point m, -1 when on the other."""
    return 1.0 if shape.contains(Point(m.x + 0.3 * n[0], m.y + 0.3 * n[1])) else -1.0


def measured_gap(ri: BaseGeometry, rj: BaseGeometry, ei: Eq, ej: Eq, tol: float = 2.0) -> float | None:
    """Median |z_i - z_j| where LiDAR measured the two planes next to each other: each plane's equation evaluated on
    its own cluster's outline within ``tol`` of the other cluster (None when they are not that close over ~2 ft)."""
    gaps = []
    for own, other in ((ri, rj), (rj, ri)):
        for part in getattr(own, "geoms", [own]):
            if part.geom_type != "Polygon":
                continue
            ring = part.exterior
            for k in range(int(ring.length / 0.5)):
                q = ring.interpolate(k * 0.5)
                if other.distance(q) <= tol:
                    gaps.append(abs(z_at(ei, q.x, q.y) - z_at(ej, q.x, q.y)))
    if len(gaps) < 8:
        return None
    gaps.sort()
    return gaps[len(gaps) // 2]


def _away(eq: Eq, shape: BaseGeometry, m: Point, n: tuple[float, float], share: float = 0.25) -> int:
    """+1 when the plane slopes down away from the line, -1 toward it, 0 when it slopes along it (its slope across
    the line under ``share`` of its slope) or is flat."""
    g = math.hypot(eq[0], eq[1])
    rise = (eq[0] * n[0] + eq[1] * n[1]) * _side(shape, m, n)  # height change walking into the plane
    if g < 1e-6 or abs(rise) < share * g:
        return 0
    return 1 if rise < 0 else -1


def _kind(line: LineString, i: int, j: int, shapes: list[Polygon], eqs: list[Eq], same_section: bool,
          measured: float | None = None) -> tuple[str, float]:
    pts = sample_line(line)
    gaps = sorted(z_at(eqs[i], x, y) - z_at(eqs[j], x, y) for x, y in pts)
    med = gaps[len(gaps) // 2]
    meet = abs(med) <= MEET_FT or (measured is not None and measured <= MEASURED_MEET_FT)
    g1, g2 = math.hypot(eqs[i][0], eqs[i][1]), math.hypot(eqs[j][0], eqs[j][1])
    if not same_section or not meet or (g1 < FLAT_SLOPE) != (g2 < FLAT_SLOPE):
        return "step", med
    if (g1 < 1e-6 and g2 < 1e-6) or (g1 > 1e-6 and g2 > 1e-6 and
                                     (eqs[i][0] * eqs[j][0] + eqs[i][1] * eqs[j][1]) / (g1 * g2) > SEAM_COS):
        return "seam", med  # one face cut in two (or a pitch break in one facing) at one height: no roof line
    (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
    ln = math.hypot(x1 - x0, y1 - y0) or 1.0
    n = (-(y1 - y0) / ln, (x1 - x0) / ln)
    m = line.interpolate(0.5, normalized=True)
    away = {_away(eqs[k], shapes[k], m, n) for k in (i, j)}
    if away == {0}:  # both run nearly along it (a mitre between two wings): the small slope across decides
        away = {_away(eqs[k], shapes[k], m, n, ACROSS_SHARE) for k in (i, j)}
    if away in ({1}, {1, 0}):  # both slope away (or one runs along it): the line falls or stays level
        plan = math.hypot(x1 - x0, y1 - y0)
        level = all(abs(z_at(eqs[k], x0, y0) - z_at(eqs[k], x1, y1)) <= max(LEVEL_FT, LEVEL_SHARE * plan) for k in (i, j))
        return ("ridge" if level else "hip"), med
    if away in ({-1}, {-1, 0}):
        return "valley", med
    return ("along" if away == {0} else "transition"), med  # {+1, -1}: the slope carries on across a pitch break


def borders(ids: list[str], shapes: list[Polygon], eqs: list[Eq], section: list[int],
            raws: list[BaseGeometry] | None = None) -> list[dict[str, Any]]:
    """Every straight border two planes share: ``{a, b, segment, length_ft, kind, step_ft, high}``.

    ``step``: across sections, or the two planes' heights differ by more than ``MEET_FT`` along it AND (when their
    clusters lie side by side) by more than ``MEASURED_MEET_FT`` where LiDAR measured them next to each other.
    Otherwise: ``seam`` for planes facing within 10 degrees of each other (or both flat; one face cut in two, not a
    roof line); ``ridge`` (level) or ``hip`` when both slope away from it (or one runs along it); ``valley`` when both
    slope toward it (or one runs along it); a short piece both planes run along (a jog where a line meets an outline
    notch) takes the kind of the longest border of the same two planes; anything else (a flat meeting a slope): ``step``.
    """
    out: list[dict[str, Any]] = []
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            if shapes[i].distance(shapes[j]) > 1e-6:
                continue
            measured = measured_gap(raws[i], raws[j], eqs[i], eqs[j]) if raws is not None else None
            merged = merge_lines(shapes[i].boundary.intersection(shapes[j].boundary))
            pair: list[dict[str, Any]] = []
            for whole in getattr(merged, "geoms", [merged]):
                for line in straight_runs(whole):
                    if line.length < 0.5:
                        continue
                    kind, med = _kind(line, i, j, shapes, eqs, section[i] == section[j], measured)
                    pair.append({"a": ids[i], "b": ids[j], "segment": [[round(x, 2), round(y, 2)] for x, y in line.coords],
                                 "length_ft": round(line.length, 1), "kind": kind, "step_ft": round(med, 2),
                                 "high": ids[i] if med >= 0 else ids[j]})
            main = max((b for b in pair if b["kind"] != "along"), key=lambda b: b["length_ft"], default=None)
            for b in pair:
                if b["kind"] == "along":
                    b["kind"] = main["kind"] if main is not None else "step"
            out += pair
    return out
