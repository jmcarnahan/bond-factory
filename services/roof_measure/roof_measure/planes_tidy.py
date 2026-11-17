"""Final tidy of the snapped planes: no spikes, no tiny edges, shared borders kept coincident (internal)."""

from __future__ import annotations

import logging
import math
from typing import Any

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .classify import polygons_of
from .planes_gaps import MIN_PLANE_SQFT, _fill_gaps, _grid, _valid

log = logging.getLogger("roof_measure.planes")

OPEN_FT = 0.25  # spikes and necks narrower than twice this are removed
SIMPLIFY_FT = 0.3  # tolerance for simplifying each plane before the shared vertices are welded
WELD_FT = 0.5  # vertices closer than this are one vertex (no edge under 0.5 ft inside the roof)
WELD_PASSES = 8  # weld, then (if overlaps or gaps appeared) trim, refill and weld again, at most this many times
OVERLAP_OK_SQFT = 0.45  # a weld that leaves less than this overlap between two planes is good enough (limit 0.5)
UNCOVERED_OK_FRACTION = 0.005  # ... and less than this share of the region uncovered (limit 1%)
MIN_ANGLE_DEG = 10.0  # interior angles under this are spike tips


def _largest(g: BaseGeometry) -> Polygon | None:
    parts = polygons_of(g)
    return max(parts, key=lambda p: p.area) if parts else None


def _open(p: Polygon) -> Polygon | None:
    """Remove spikes and zero-width necks: erode then dilate with mitre joins, keep the largest part."""
    return _largest(_valid(p.buffer(-OPEN_FT, join_style=2).buffer(OPEN_FT, join_style=2)))


def resolve_overlaps(planes: list[Polygon | None]) -> list[Polygon | None]:
    """Make the planes disjoint again: the larger plane keeps an overlap; a plane keeps its largest part."""
    order = sorted((i for i, p in enumerate(planes) if p is not None), key=lambda i: (-planes[i].area, i))  # type: ignore[union-attr]
    taken: BaseGeometry = Polygon()
    out: list[Polygon | None] = [None] * len(planes)
    for i in order:
        piece = _valid(_grid(planes[i].difference(taken)))  # type: ignore[union-attr]
        taken = _valid(_grid(taken.union(planes[i])))  # type: ignore[arg-type]
        part = _largest(piece)
        out[i] = part if part is not None and part.area >= MIN_PLANE_SQFT else None
    return out


def _max_overlap(planes: list[Polygon | None]) -> float:
    live = [p for p in planes if p is not None]
    return max((a.intersection(b).area for i, a in enumerate(live) for b in live[i + 1:]), default=0.0)


def _uncovered(planes: list[Polygon | None], region: BaseGeometry) -> float:
    live = [p for p in planes if p is not None]
    return float(region.difference(unary_union(live)).area) if live else float(region.area)


def tidy(cur: list[Polygon | None], region: BaseGeometry) -> list[Polygon | None]:
    """Open each plane, hand the removed bits to neighbours, simplify, weld shared vertices, resolve overlaps."""
    opened = [None if p is None else _open(_grid(p)) for p in cur]
    opened = [None if p is None else _grid(p) for p in opened]
    opened = _fill_gaps(opened, region, split=False)  # the bits the opening removed are gaps again
    simp: list[Polygon | None] = []
    for p in opened:  # each plane alone: both neighbours of a stretch keep its end vertices, so both get one chord
        q = None if p is None else _largest(_valid(_grid(p.simplify(SIMPLIFY_FT, preserve_topology=True))))
        simp.append(q if q is not None else p)
    out = _fill_gaps(resolve_overlaps(simp), region, split=False)  # the leftovers are slivers
    for _ in range(WELD_PASSES):  # the last step is always a weld, so the result has no tiny edges or spikes
        out = weld(out)
        if _max_overlap(out) <= OVERLAP_OK_SQFT and _uncovered(out, region) <= UNCOVERED_OK_FRACTION * region.area:
            break
        out = _fill_gaps(resolve_overlaps(out), region, split=False)  # welding moved vertices: trim and refill
    else:
        out = weld(out)  # out of passes: finish on a weld anyway
    return out


def weld(planes: list[Polygon | None]) -> list[Polygon | None]:
    """Merge vertices closer than ``WELD_FT`` (the same way on every plane, so shared borders stay shared), then
    drop spike tips (angles under 10 degrees) and repeated points."""
    seen: set[tuple[float, float]] = set()
    pts: list[tuple[float, float]] = []
    for p in planes:
        for ring in ([] if p is None else [p.exterior, *p.interiors]):
            for x, y in ring.coords:
                if (x, y) not in seen:
                    seen.add((x, y))
                    pts.append((x, y))
    parent = list(range(len(pts)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    grid: dict[tuple[int, int], list[int]] = {}
    for i, (x, y) in enumerate(pts):
        gx, gy = int(x // WELD_FT), int(y // WELD_FT)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grid.get((gx + dx, gy + dy), []):
                    if math.dist(pts[i], pts[j]) < WELD_FT:
                        parent[find(i)] = find(j)
        grid.setdefault((gx, gy), []).append(i)
    groups: dict[int, list[int]] = {}
    for i in range(len(pts)):
        groups.setdefault(find(i), []).append(i)
    target: dict[tuple[float, float], tuple[float, float]] = {}
    for members in groups.values():
        cx = round(sum(pts[i][0] for i in members) / len(members), 2)
        cy = round(sum(pts[i][1] for i in members) / len(members), 2)
        for i in members:
            target[pts[i]] = (cx, cy)

    def ring(r: Any) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for c in r.coords[:-1]:
            q = target.get((c[0], c[1]), (c[0], c[1]))
            if not out or q != out[-1]:
                out.append(q)
        while len(out) > 1 and out[0] == out[-1]:
            out.pop()
        return out

    result: list[Polygon | None] = []
    for p in planes:
        if p is None:
            result.append(None)
            continue
        shell = _drop_spikes(ring(p.exterior))
        holes = [h for h in (_drop_spikes(ring(r)) for r in p.interiors) if len(h) >= 3]
        q = _valid(Polygon(shell, holes)) if len(shell) >= 3 else Polygon()
        parts = polygons_of(q)
        keep = max(parts, key=lambda g: g.area) if parts else None
        if keep is None or keep.area < MIN_PLANE_SQFT:  # the welded ring failed: keep this plane unwelded, say so
            log.warning("plane %d kept unwelded (its welded ring was empty or too small)", len(result))
            keep = p
        result.append(keep)
    return result


def _drop_spikes(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Remove vertices whose interior angle is under 10 degrees (and collinear ones), repeatedly."""
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
            n1, n2 = math.hypot(*v1), math.hypot(*v2)
            cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2) if n1 > 0 and n2 > 0 else 1.0
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
            if ang < MIN_ANGLE_DEG or ang > 179.9:
                pts = pts[:i] + pts[i + 1:]
                changed = True
                break
    return pts
