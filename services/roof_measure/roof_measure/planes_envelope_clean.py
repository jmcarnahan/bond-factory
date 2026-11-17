"""Final cleanup of the envelope planes (internal): weld near vertices and drop collinear ones, the same way in every
polygon so that shared borders keep identical vertices on both sides."""

from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from .classify import polygons_of

Pt = tuple[float, float]
THIN_FT = 3.0  # a plane's part narrower than this along the outline may go to its neighbour


def weld(polys: list[Polygon], outline: BaseGeometry, tol: float) -> list[Polygon]:
    """Vertices closer than ``tol`` merged into one, the same way in every polygon (shared borders stay shared); a
    vertex on the outline stays where it is and pulls its neighbours onto it; two outline vertices are never merged.
    Returns the input when the result would not be valid."""
    pts = sorted({q for g in polys for r in [g.exterior, *g.interiors] for q in list(r.coords)[:-1]})
    on = {q: outline.distance(Point(q)) < 0.05 for q in pts}
    parent = {q: q for q in pts}

    def find(q: Pt) -> Pt:
        while parent[q] != q:
            q = parent[q]
        return q

    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            if b[0] - a[0] > tol:
                break
            if math.dist(a, b) < tol and not (on[a] and on[b]):
                ra, rb = find(a), find(b)
                if ra == rb or (on[ra] and on[rb]):
                    continue
                keep, gone = (ra, rb) if on[ra] or (not on[rb] and ra < rb) else (rb, ra)  # an outline vertex is the root
                parent[gone] = keep
    groups: dict[Pt, list[Pt]] = {}
    for q in pts:
        groups.setdefault(find(q), []).append(q)
    target = {}
    for members in groups.values():
        fixed = [q for q in members if on[q]]
        c = fixed[0] if fixed else (sum(q[0] for q in members) / len(members), sum(q[1] for q in members) / len(members))
        for q in members:
            target[q] = c
    out = []
    for g in polys:
        rings = []
        for r in [g.exterior, *g.interiors]:
            ring: list[Pt] = []
            for q in list(r.coords)[:-1]:
                t = target[q]
                if not ring or ring[-1] != t:
                    ring.append(t)
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring.pop()
            rings.append(ring)
        if len(rings[0]) < 3:
            return polys
        q = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3])
        if not q.is_valid or q.is_empty:
            return polys
        out.append(q)
    return out


def _distinct(pts: list[Pt]) -> list[Pt]:
    """The ring's points without consecutive repeats (a repeated vertex looks collinear with itself)."""
    out: list[Pt] = []
    for q in pts:
        if not out or math.dist(q, out[-1]) > 0.05:
            out.append(q)
    while len(out) > 1 and math.dist(out[0], out[-1]) <= 0.05:
        out.pop()
    return out


def drop_collinear(polys: list[Polygon], tol: float = 0.02) -> list[Polygon]:
    """Remove every vertex that is collinear (within ``tol`` ft) in EVERY polygon that has it, so shared borders keep
    identical vertices on both sides."""
    keep_votes: dict[Pt, bool] = {}
    for g in polys:
        for ring in [g.exterior, *g.interiors]:
            pts = _distinct(list(ring.coords)[:-1])
            n = len(pts)
            for i in range(n):
                a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
                needed = LineString([a, c]).distance(Point(b)) > tol or math.dist(a, c) < 1e-9
                keep_votes[b] = keep_votes.get(b, False) or needed
    out = []
    for g in polys:
        rings = []
        for ring in [g.exterior, *g.interiors]:
            pts = [q for q in _distinct(list(ring.coords)[:-1]) if keep_votes.get(q, True)]
            rings.append(pts)
        q = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3]) if len(rings[0]) >= 3 else g
        out.append(q if q.is_valid and not q.is_empty else g)
    return out


def collapse_junction_edges(polys: list[Polygon], outline: BaseGeometry, tol: float) -> list[Polygon]:
    """An edge shorter than ``tol`` between two junctions (vertices of three or more planes, away from the outline)
    is a junction that did not quite close: it collapses onto the end whose other edges are longer (so the main roof
    line stays straight and the short lines bend a little into it). Returns the input when the result is invalid."""
    count: dict[Pt, int] = {}
    incident: dict[Pt, float] = {}
    edges: dict[tuple[Pt, Pt], float] = {}
    for g in polys:
        for r in [g.exterior, *g.interiors]:
            pts = list(r.coords)[:-1]
            for q in set(pts):
                count[q] = count.get(q, 0) + 1
            for k, a in enumerate(pts):
                b = pts[(k + 1) % len(pts)]
                ln = math.dist(a, b)
                edges[(min(a, b), max(a, b))] = ln
                incident[a] = incident.get(a, 0.0) + ln
                incident[b] = incident.get(b, 0.0) + ln
    move: dict[Pt, Pt] = {}
    for (a, b), ln in sorted(edges.items(), key=lambda e: e[1]):
        if ln >= tol or a in move or b in move or count.get(a, 0) < 3 or count.get(b, 0) < 3:
            continue
        if outline.distance(Point(a)) < 0.05 or outline.distance(Point(b)) < 0.05:
            continue
        keep, gone = (a, b) if incident[a] - ln >= incident[b] - ln else (b, a)
        move[gone] = keep
    if not move:
        return polys
    out = []
    for g in polys:
        rings = []
        for r in [g.exterior, *g.interiors]:
            ring: list[Pt] = []
            for q in list(r.coords)[:-1]:
                t = move.get(q, q)
                if not ring or ring[-1] != t:
                    ring.append(t)
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring.pop()
            rings.append(ring)
        if len(rings[0]) < 3:
            return polys
        q = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 3])
        if not q.is_valid or q.is_empty:
            return polys
        out.append(q)
    return out


def rehome_detached(polys: list[BaseGeometry], raws: list[BaseGeometry]) -> list[BaseGeometry]:
    """Each plane keeps its main part (the one holding most of its cluster); every other part joins the plane it
    shares the longest border with (nothing is dropped)."""
    out: list[BaseGeometry] = list(polys)
    for _ in range(3):
        moved = False
        for k, g in enumerate(out):
            parts = polygons_of(g)
            if len(parts) < 2:
                continue
            main = max(parts, key=lambda p: (p.intersection(raws[k]).area if not raws[k].is_empty else 0.0, p.area))
            out[k] = main
            for part in parts:
                if part is main:
                    continue
                nbs = [(part.boundary.intersection(o.boundary).length, j) for j, o in enumerate(out) if j != k and not o.is_empty]
                ln, j = max(nbs, default=(0.0, -1))
                if j >= 0 and ln > 0:
                    out[j] = out[j].union(part)
                    moved = True
        if not moved:
            break
    return [max(polygons_of(g), key=lambda p: p.area) if polygons_of(g) else Polygon() for g in out]


def thin_strips(polys: list[BaseGeometry], raws: list[BaseGeometry], fp: Polygon) -> list[BaseGeometry]:
    """A part of a plane narrower than ``THIN_FT`` that lies along the outline (a strip between a roof line and an
    outline notch) and that its own cluster covers less than the neighbour's goes to the neighbour across its
    longest border."""
    out = list(polys)
    for k, g in enumerate(polys):
        if g.is_empty:
            continue
        thin = g.difference(g.buffer(-THIN_FT / 2, join_style=2).buffer(THIN_FT / 2, join_style=2))
        for piece in polygons_of(thin):
            if piece.area < 1.0 or piece.boundary.intersection(fp.exterior.buffer(0.05)).length < 1.0:
                continue
            own = piece.intersection(raws[k]).area if not raws[k].is_empty else 0.0
            if own >= 0.6 * piece.area:
                continue
            nbs = [(piece.boundary.intersection(o.boundary).length, j) for j, o in enumerate(out) if j != k and not o.is_empty]
            ln, j = max(nbs, default=(0.0, -1))
            if j < 0 or ln < 0.5 or piece.intersection(raws[j]).area < own:
                continue
            rest = polygons_of(out[k].difference(piece))
            grown = polygons_of(out[j].union(piece))
            if len(grown) != 1 or not rest:
                continue
            out[k], out[j] = max(rest, key=lambda q: q.area), grown[0]
    return out


def node_rings(polys: list[Polygon], tol: float = 0.02) -> list[Polygon]:
    """Every vertex of one polygon that lies on another polygon's edge (within ``tol``, not at its ends) is added to
    that edge, so two planes whose borders meet in a T (a section's roof line ending on a step line) share the
    border's vertices and the border is found. Returns the input when the result would not be valid."""
    from shapely import STRtree

    pts = sorted({q for g in polys for r in [g.exterior, *g.interiors] for q in list(r.coords)[:-1]})
    if not pts:
        return polys
    tree = STRtree([Point(q) for q in pts])
    out = []
    for g in polys:
        rings = []
        for r in [g.exterior, *g.interiors]:
            ring = list(r.coords)[:-1]
            own = set(ring)
            new: list[Pt] = []
            for k, a in enumerate(ring):
                b = ring[(k + 1) % len(ring)]
                new.append(a)
                seg = LineString([a, b])
                ln = seg.length
                if ln <= 2 * tol:
                    continue
                hits = [pts[i] for i in tree.query(seg.buffer(tol))]
                extra = sorted((seg.project(Point(q)), q) for q in hits
                               if q not in own and seg.distance(Point(q)) <= tol < seg.project(Point(q)) < ln - tol)
                new += [q for _, q in extra]
            rings.append(new)
        q = Polygon(rings[0], rings[1:])
        if not q.is_valid or q.is_empty:
            return polys
        out.append(q)
    return out
