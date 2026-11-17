"""Gap filling for the snapped planes: who gets the part of the roof no LiDAR plane covers (internal)."""

from __future__ import annotations

import logging

from shapely.errors import ShapelyError
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .classify import polygons_of

log = logging.getLogger("roof_measure.planes")

GRID_FT = 0.01  # all geometry lives on this grid, so shared edges stay shared
MIN_PLANE_SQFT = 4.0  # smaller pieces are dropped (slivers)
MAX_BRIDGE_FT = 3.0  # a gap island this near a plane (but not touching it) is joined by a thin bridge
MIN_SHARED_FT = 0.5  # a border shorter than this does not count as touching
DOMINANT_SHARE = 0.7  # one plane with this share of a gap's border takes the whole gap
SAMPLE_FT = 0.5  # spacing of the outline points the nearest-plane split is built on


def _grid(g: BaseGeometry) -> BaseGeometry:
    from shapely import set_precision

    return set_precision(g, GRID_FT) if not g.is_empty else g


def _valid(g: BaseGeometry) -> BaseGeometry:
    return g if g.is_valid else g.buffer(0)


def _shared_ft(a: BaseGeometry, b: BaseGeometry) -> float:
    return float(a.boundary.intersection(b.boundary).length)


def _bridge(gap: Polygon, plane: Polygon) -> BaseGeometry:
    """Join an island to a plane by a thin strip along the shortest line between them."""
    from shapely.ops import nearest_points

    p1, p2 = nearest_points(plane, gap)
    return LineString([p1, p2]).buffer(0.3)



def _resolve_overlaps(cleaned: list[Polygon], region: BaseGeometry, clip: bool) -> list[Polygon | None]:
    """Disjoint copies of the planes (the larger plane keeps an overlap), inside ``region`` when clipping."""
    order = sorted(range(len(cleaned)), key=lambda i: (-cleaned[i].area, i))
    taken: BaseGeometry = Polygon()
    own: list[Polygon | None] = [None] * len(cleaned)
    for i in order:
        piece = _valid(_grid(cleaned[i].intersection(region) if clip else cleaned[i]))
        piece = _valid(_grid(piece.difference(taken)))
        taken = _valid(_grid(taken.union(cleaned[i].intersection(region) if clip else cleaned[i])))
        parts = [p for p in polygons_of(piece) if p.area >= MIN_PLANE_SQFT]
        own[i] = max(parts, key=lambda p: p.area) if parts else None
    return own


def _split_by_nearest(gap: Polygon, cur: list[Polygon | None], ids: list[int]) -> dict[int, BaseGeometry]:
    """Cut ``gap`` into the parts nearest to each plane in ``ids`` (Voronoi cells of the planes' outlines)."""
    from shapely import STRtree, make_valid, segmentize, set_precision
    from shapely.geometry import MultiPoint, Point
    from shapely.ops import voronoi_diagram

    pts: list[Point] = []
    owner: list[int] = []
    for i in ids:
        ring = segmentize(cur[i].exterior, SAMPLE_FT)  # type: ignore[union-attr]
        for x, y in ring.coords:
            pts.append(Point(x, y))
            owner.append(i)
    cells = voronoi_diagram(MultiPoint(pts), envelope=gap.buffer(5.0).envelope)
    tree = STRtree(pts)
    by_owner: dict[int, list[BaseGeometry]] = {}
    for cell in cells.geoms:
        hit = tree.query(cell, predicate="contains")
        if len(hit):  # jittered outlines give cells GEOS calls invalid: repair and snap them before the union
            by_owner.setdefault(owner[int(hit[0])], []).append(set_precision(make_valid(cell), GRID_FT))
    out: dict[int, BaseGeometry] = {}
    for i, cs in by_owner.items():
        part = _valid(_grid(unary_union(cs).intersection(gap)))
        if not part.is_empty:
            out[i] = part
    return out


def _pieces_for(g: Polygon, cur: list[Polygon | None], split: bool) -> dict[int, BaseGeometry]:
    """Which plane takes which part of one gap (empty: nobody, the gap stays uncovered)."""
    shared = {i: n for i, p in enumerate(cur) if p is not None and (n := _shared_ft(g, p)) > MIN_SHARED_FT}
    if not shared:  # an island: the nearest plane within reach, joined by a bridge
        near = min(((g.distance(p), i) for i, p in enumerate(cur) if p is not None), default=None)
        if near is None or near[0] > MAX_BRIDGE_FT:
            return {}
        return {near[1]: g.union(_bridge(g, cur[near[1]]))}  # type: ignore[arg-type]
    best = max(shared, key=lambda i: (shared[i], -i))
    if not split or shared[best] >= DOMINANT_SHARE * sum(shared.values()):
        return {best: g}
    try:
        return _split_by_nearest(g, cur, sorted(shared))
    except (ShapelyError, ValueError):  # one bad gap must never lose the roof: it goes whole to the longest border
        log.warning("gap split failed; gave the gap to the plane with the longest shared border", exc_info=True)
        return {best: g}


def _fill_gaps(own: list[Polygon | None], region: BaseGeometry, split: bool = True) -> list[Polygon | None]:
    """Give every uncovered part of the region to a plane.

    A gap that one plane dominates (at least 70% of the border it shares with planes) goes whole to that plane; a
    gap between several planes is cut at the middle (each part to the nearest plane); an island that touches none
    goes to the nearest plane within 3 ft by a thin bridge, else it stays uncovered. A gap that raises a geometry
    error is given whole to the longest-border plane, or left uncovered if even that fails.
    """
    cur = list(own)
    for _ in range(3):  # a first pass can leave a remainder when a plane could not take its piece whole
        live = [p for p in cur if p is not None]
        if not live:
            return cur
        gap = _valid(_grid(region.difference(unary_union(live))))
        parts = [g for g in polygons_of(gap) if g.area > 0.05]
        if not parts:
            break
        grew = False
        for g in sorted(parts, key=lambda p: -p.area):
            try:
                pieces = _pieces_for(g, cur, split)
            except (ShapelyError, ValueError):
                log.warning("a gap could not be assigned and stays uncovered", exc_info=True)
                continue
            for i, piece in pieces.items():
                try:
                    merged = _valid(_grid(cur[i].union(piece)))  # type: ignore[union-attr]
                except (ShapelyError, ValueError):
                    log.warning("a gap piece could not be merged and stays uncovered", exc_info=True)
                    continue
                parts_m = polygons_of(merged)
                if parts_m:
                    cur[i] = max(parts_m, key=lambda p: p.area)
                    grew = True
        if not grew:
            break
    return cur
