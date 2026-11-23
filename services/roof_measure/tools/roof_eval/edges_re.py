"""The edge set recomputed from the facets (an engine's own edge list is not taken on trust).

Facets that share a boundary (within 5 cm) give interior edges; boundary pieces shared with no other facet give outline
edges. Types come from geometry only:
  * interior, jump measured FROM THE REFERENCE POINTS on both sides >= 0.3 m: level_change (below 0.3 m the edge is a crease);
    fewer than 5 points on a side: the jump cannot be measured, the edge is ``level_change_unverified`` when the two planes
    differ by 0.3 m or more there (reported separately, never counted as a verified level change);
  * crease: both facets fall away from the edge = ridge (horizontal) or hip; both rise = valley; else transition (a seam
    inside one surface: also the mergeable pairs below);
  * outline: flat facet = flat_edge; pitched facet = eave (level, the facet rises away from it), rake (sloped, or the level HIGH
    edge, flagged ``high_edge``: contract convention, never ridge or eave).
``adjacent_pairs`` lists the neighbouring facet pairs with their shared length and whether their planes agree within
0.07 m at the shared boundary and 3 degrees (coplanar neighbours that should be one facet).
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree

from .geom import Edge, Facet, Roof
from .m_fit import FALSE_JUMP_M, edge_jump_m

SHARE_TOL_M = 0.05
MIN_SEG_M = 0.3
MIN_PAIR_M = 0.5
SLOPE_EPS = 0.02
HORIZONTAL = 0.1
MERGE_DZ_M = 0.07
MERGE_ANGLE_DEG = 3.0
UNMARKED_MATCH_M = 0.5


@dataclass
class Recomputed:
    edges: list[Edge]
    unverified_ft: float
    pairs: int
    mergeable: int


def _lines(g) -> list[LineString]:
    if g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    return [x for part in getattr(g, "geoms", []) for x in _lines(part)]


def _segments(g) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out = []
    for ln in _lines(linemerge(g) if g.geom_type == "MultiLineString" else g):
        c = list(ln.coords)
        out += [(a[:2], b[:2]) for a, b in itertools.pairwise(c) if math.dist(a[:2], b[:2]) >= MIN_SEG_M]
    return out


def _into(f: Facet, a, b) -> np.ndarray:
    """Unit plan normal of segment a-b pointing into facet ``f``."""
    d = np.array([b[0] - a[0], b[1] - a[1]])
    n = np.array([-d[1], d[0]]) / max(np.hypot(*d), 1e-12)
    mid = np.array([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])
    for step in (0.05, 0.15):  # a probe just beside the edge: right even for a concave facet
        if f.poly.contains(Point(*(mid + step * n))):
            return n
        if f.poly.contains(Point(*(mid - step * n))):
            return -n
    c = f.poly.representative_point()
    return n if np.dot(np.array([c.x, c.y]) - mid, n) >= 0 else -n


def _edge3(f: Facet, a, b, t: str, fids: list[str]) -> Edge:
    return Edge(t, (a[0], a[1], f.z_at(*a)), (b[0], b[1], f.z_at(*b)), fids)


def _crease(p: Facet, q: Facet, a, b) -> str:
    n = _into(p, a, b)
    sp = p.plane[0] * n[0] + p.plane[1] * n[1]
    sq = -(q.plane[0] * n[0] + q.plane[1] * n[1])
    if sp < -SLOPE_EPS and sq < -SLOPE_EPS:
        run = math.dist(a, b)
        return "ridge" if abs(p.z_at(*a) - p.z_at(*b)) <= HORIZONTAL * run else "hip"
    if sp > SLOPE_EPS and sq > SLOPE_EPS:
        return "valley"
    return "transition"


def _mergeable(p: Facet, q: Facet, segs) -> bool:
    dz = 0.0
    for a, b in segs:
        for t in (0.0, 0.5, 1.0):
            x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            dz = max(dz, abs(p.z_at(x, y) - q.z_at(x, y)))
    na, nb = np.array([-p.plane[0], -p.plane[1], 1.0]), np.array([-q.plane[0], -q.plane[1], 1.0])
    ang = math.degrees(math.acos(float(np.clip(na @ nb / np.linalg.norm(na) / np.linalg.norm(nb), -1, 1))))
    return dz <= MERGE_DZ_M and ang <= MERGE_ANGLE_DEG


def recompute(roof: Roof, ref: np.ndarray) -> Recomputed:
    """Interior and outline edges from the facets; see the module docstring."""
    fs = [f for f in roof.facets if not f.poly.is_empty and f.poly.geom_type == "Polygon"]
    edges: list[Edge] = []
    unver = 0.0
    pairs = merge = 0
    shared_by: dict[int, list] = {i: [] for i in range(len(fs))}
    tree = STRtree([f.poly for f in fs])
    for i, p in enumerate(fs):
        for j in tree.query(p.poly.buffer(SHARE_TOL_M)):
            if j <= i:
                continue
            q = fs[int(j)]
            if p.poly.distance(q.poly) > SHARE_TOL_M:
                continue
            segs = _segments(p.poly.boundary.intersection(q.poly.buffer(SHARE_TOL_M)))
            if not segs:
                continue
            shared_by[i].append(q.poly)
            shared_by[int(j)].append(p.poly)
            if sum(math.dist(a, b) for a, b in segs) >= MIN_PAIR_M:
                pairs += 1
                merge += _mergeable(p, q, segs)
            for a, b in segs:
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                lo = p if p.z_at(*mid) <= q.z_at(*mid) else q
                gap = max(abs(p.z_at(*a) - q.z_at(*a)), abs(p.z_at(*b) - q.z_at(*b)))
                jump = edge_jump_m(ref, (*a, 0.0), (*b, 0.0))
                fids = [p.id, q.id]
                if jump is not None and jump >= FALSE_JUMP_M:
                    edges.append(_edge3(lo, a, b, "level_change", fids))
                elif jump is None and gap >= FALSE_JUMP_M:
                    edges.append(_edge3(lo, a, b, "level_change_unverified", fids))
                    unver += edges[-1].length_ft
                else:
                    edges.append(_edge3(p, a, b, _crease(p, q, a, b), fids))
    for i, f in enumerate(fs):
        free = f.poly.boundary
        if shared_by[i]:
            free = f.poly.boundary.difference(unary_union(shared_by[i]).buffer(SHARE_TOL_M))
            # the cut above also trims SHARE_TOL_M off each free end at a junction: give it back
            free = f.poly.boundary.intersection(free.buffer(SHARE_TOL_M * 1.01)) if not free.is_empty else free
        for a, b in _segments(free):
            run = math.dist(a, b)
            level = abs(f.z_at(*a) - f.z_at(*b)) <= HORIZONTAL * run
            n = _into(f, a, b)
            high = (not f.is_flat) and level and (f.plane[0] * n[0] + f.plane[1] * n[1]) < -SLOPE_EPS  # the facet falls away from it
            t = "flat_edge" if f.is_flat else ("eave" if level and not high else "rake")
            edges.append(_edge3(f, a, b, t, [f.id]))
            edges[-1].high_edge = high
    return Recomputed(edges, unver, pairs, merge)


def unmarked_level_change_ft(rec: Recomputed, engine_edges: list[Edge]) -> float:
    """Feet of verified level change (recomputed) that the engine did not type level_change (no engine level_change edge
    within 0.5 m of the segment's midpoint)."""
    marked = [LineString([e.p0[:2], e.p1[:2]]) for e in engine_edges if e.type == "level_change"]
    tot = 0.0
    for e in rec.edges:
        if e.type != "level_change":
            continue
        mid = Point((e.p0[0] + e.p1[0]) / 2, (e.p0[1] + e.p1[1]) / 2)
        if not any(m.distance(mid) <= UNMARKED_MATCH_M for m in marked):
            tot += e.length_ft
    return tot


def disagreement_ft(recomputed: list[Edge], engine: list[Edge]) -> float:
    """Sum over edge types of |recomputed feet - the engine's feet| (types: eave rake ridge hip valley flat_edge level_change)."""
    types = ("eave", "rake", "ridge", "hip", "valley", "flat_edge", "level_change")
    a, b = {t: 0.0 for t in types}, {t: 0.0 for t in types}
    for e in recomputed:
        if e.type in a:
            a[e.type] += e.length_ft
    for e in engine:
        if e.type in b:
            b[e.type] += e.length_ft
    return sum(abs(a[t] - b[t]) for t in types)


def summary(rec: Recomputed, roof: Roof) -> dict[str, Any]:
    tot = sum(e.length_ft for e in rec.edges)
    return {"edge_len_ft": tot, "level_change_unverified_ft": rec.unverified_ft, "adjacent_pairs": rec.pairs,
            "mergeable_pairs": rec.mergeable, "mergeable_neighbour_share": rec.mergeable / rec.pairs if rec.pairs else None,
            "edge_list_disagreement_ft": disagreement_ft(rec.edges, roof.engine_edges),
            "unmarked_level_change_ft": unmarked_level_change_ft(rec, roof.engine_edges)}
