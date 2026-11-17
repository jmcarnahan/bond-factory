"""Snapped LiDAR planes: the raw plane blocks made disjoint, gap-free and clipped to the roof outline.

Pure geometry (shapely only); internal to the library (not exported from the package). The planes are the evidence
the quality metrics compare the model against and the picture of what LiDAR saw; they never feed the model itself.
Input blocks are the ``bond.roof_blocks/0.1`` planes. Gap filling lives in ``planes_gaps``, the final tidy in
``planes_tidy``.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from shapely.errors import ShapelyError
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .classify import BlockSet, clean_polygon, polygons_of
from .planes_gaps import MIN_PLANE_SQFT, _fill_gaps, _grid, _resolve_overlaps, _valid
from .planes_straight import straighten_with_borders as _straighten_with_borders
from .planes_tidy import tidy

log = logging.getLogger("roof_measure.planes")


@dataclass
class Plane:
    """One snapped plane. ``polygon`` is a closed-ring-less CCW list of [x, y] in feet (model frame)."""

    id: str
    polygon: list[list[float]]
    pitch_rise: float
    aspect_deg: float | None
    plan_area_sqft: float
    surface_area_sqft: float
    height_ft: float
    rms_ft: float
    filled_pct: float
    holes: list[list[list[float]]] = field(default_factory=list)  # rings of other planes lying inside this one
    straightened: bool = False  # the outline was redrawn with few vertices and straight shared sides (planes_straight)
    raw_plan_area_sqft: float | None = None  # the area of the raw LiDAR cluster this plane grew from
    straighten_method: str | None = None  # 'envelope' | 'arrangement' (planes_envelope); None for the in-place method
    section: int | None = None  # roof section number (planes_envelope)
    raw_polygon: list[list[float]] | None = None  # the raw LiDAR cluster outline (object only: not in to_dict)
    plane_eq: list[float] | None = None  # [a, b, c]: z = a x + b y + c, feet above ground, plan feet (additive, 0.4.0)

    def shape(self) -> Polygon:
        """The plane as a shapely polygon (holes included)."""
        return Polygon(self.polygon, self.holes)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id, "polygon": [list(p) for p in self.polygon], "pitch_rise": self.pitch_rise,
            "aspect_deg": self.aspect_deg, "plan_area_sqft": self.plan_area_sqft,
            "surface_area_sqft": self.surface_area_sqft, "height_ft": self.height_ft, "rms_ft": self.rms_ft,
            "filled_pct": self.filled_pct}
        if self.raw_plan_area_sqft is not None:  # additive (0.4.0): set by snapping
            d["straightened"] = self.straightened
            d["raw_plan_area_sqft"] = self.raw_plan_area_sqft
        if self.straighten_method is not None:
            d["straighten_method"] = self.straighten_method
        if self.section is not None:
            d["section"] = self.section
        if self.plane_eq is not None:
            d["plane_eq"] = list(self.plane_eq)
        if self.holes:  # optional: only a plane that has another plane inside it carries the key
            d["holes"] = [[list(p) for p in ring] for ring in self.holes]
        return d


@dataclass
class SnapResult:
    """The planes plus the numbers only the snapping step knows.

    ``footprint_area_sqft`` is the outline's area and ``raw_in_footprint_sqft`` the part of it the raw cleaned planes
    covered before any gap filling, whether or not the planes were clipped. ``failed`` is True when snapping could
    not run (a geometry error), as opposed to "ran and found no plane".
    """

    planes: list[Plane] = field(default_factory=list)
    borders: list[dict[str, Any]] = field(default_factory=list)  # shared borders (planes_straight.plane_borders)
    footprint_area_sqft: float = 0.0
    raw_in_footprint_sqft: float = 0.0
    failed: bool = False
    bad_blocks: int = 0  # LiDAR blocks left out because a number in them was NaN or infinite

    @property
    def covered_pct(self) -> float | None:
        a = self.footprint_area_sqft
        return min(100.0, 100.0 * self.raw_in_footprint_sqft / a) if a > 0 else None


def _finite(b: Any) -> bool:
    """False when any coordinate or number of the block is NaN or infinite."""
    nums = [c for pt in b.polygon_ft for c in pt] + [b.pitch_rise, b.height_above_ground_ft, b.rms_ft,
                                                      b.plan_area_sqft, b.mean_z_ft]
    if b.aspect_deg is not None:
        nums.append(b.aspect_deg)
    return all(math.isfinite(float(n)) for n in nums)


def _ring(ring: Any) -> list[list[float]]:
    return [[round(float(x), 2) + 0.0, round(float(y), 2) + 0.0] for x, y in list(ring.coords)[:-1]]


def _region(cleaned: list[Polygon], footprint: Polygon, clip: bool) -> BaseGeometry:
    if clip:
        return footprint
    union = unary_union(cleaned)
    return _valid(union.buffer(2.0).buffer(-2.0).union(union))  # closing: fills holes and slits inside the roof


def snap_with_stats(blockset: BlockSet, footprint_polygon: Polygon | list[Any] | None = None, *,
                    clip_to_footprint: bool = True, straighten: bool = True) -> SnapResult:
    """Snap the LiDAR planes of ``blockset``; see ``snap_planes``. Never raises.

    Degenerate input (no blocks, a footprint without area) gives no planes with ``failed`` False; a geometry error
    that stopped the work gives no planes with ``failed`` True (and is logged).
    """
    try:
        return _snap(blockset, footprint_polygon, clip_to_footprint, straighten)
    except (ShapelyError, ValueError, TypeError, ArithmeticError, IndexError):
        log.warning("plane snapping failed", exc_info=True)
        return SnapResult(failed=True)


def _snap(blockset: BlockSet, footprint_polygon: Polygon | list[Any] | None, clip: bool,
          straighten: bool = True) -> SnapResult:
    fp = footprint_polygon if isinstance(footprint_polygon, Polygon) else (
        Polygon(footprint_polygon) if footprint_polygon is not None else blockset.footprint)
    fp = _valid(fp)
    sane = [b for b in blockset.blocks if b.kind in ("flat", "sloped") and _finite(b)]
    bad = sum(1 for b in blockset.blocks if b.kind in ("flat", "sloped")) - len(sane)  # non-finite blocks are dropped
    blocks = [b for b in sane if b.poly.area > 0]
    if fp.is_empty or fp.area <= 0 or not blocks:
        area = 0.0 if fp.is_empty else float(fp.area)  # no usable block: nothing covers the outline (0%)
        return SnapResult(footprint_area_sqft=area if blockset.blocks else 0.0, bad_blocks=bad)
    fp = _valid(_grid(max(polygons_of(fp), key=lambda p: p.area)))
    cleaned = [_valid(clean_polygon(b.poly)) for b in blocks]
    cleaned = [max(polygons_of(c), key=lambda p: p.area) if polygons_of(c) else Polygon() for c in cleaned]
    region = _region(cleaned, fp, clip)
    if region.is_empty:
        return SnapResult(footprint_area_sqft=float(fp.area), bad_blocks=bad)
    raw = _resolve_overlaps(cleaned, region, clip)
    raw_in_fp = sum(r.intersection(fp).area for r in raw if r is not None)  # coverage is always measured on the outline
    final = tidy(_fill_gaps(raw, region), region)
    grounds = sorted(float(b.mean_z_ft) - float(b.height_above_ground_ft) for b in blocks)
    datum = grounds[len(grounds) // 2] if len(grounds) % 2 else (grounds[len(grounds) // 2 - 1] + grounds[len(grounds) // 2]) / 2
    planes: list[Plane] = []
    for b, r, f in zip(blocks, raw, final, strict=True):
        if f is None or f.area < MIN_PLANE_SQFT:
            continue
        flat = b.kind == "flat"
        pitch = 0.0 if flat else float(b.pitch_rise)
        plan = float(f.area)
        filled = max(0.0, plan - (r.area if r is not None else 0.0))
        f = orient(f, 1.0)
        cen = b.poly.centroid  # the plane equation is the LiDAR fit: its height h is the mean height at the cluster's centroid
        sl = 0.0 if flat else pitch / 12.0
        asp = math.radians(b.aspect_deg or 0.0)
        gx, gy = -sl * math.sin(asp), -sl * math.cos(asp)  # the height rises away from the downslope (aspect) direction
        h = float(b.mean_z_ft) - datum  # one height datum for the whole roof (blocks' local grounds differ by feet)
        planes.append(Plane(
            raw_polygon=[[round(x, 2), round(y, 2)] for x, y in list(max(polygons_of(b.poly), key=lambda q: q.area).exterior.coords)[:-1]],
            plane_eq=[round(gx, 5), round(gy, 5), round(h - gx * cen.x - gy * cen.y, 3)],
            id=b.id, polygon=_ring(f.exterior), holes=[_ring(h) for h in f.interiors], pitch_rise=round(pitch, 2),
            aspect_deg=None if flat else b.aspect_deg,
            plan_area_sqft=round(plan, 1), surface_area_sqft=round(plan / math.cos(math.atan(pitch / 12.0)), 1),
            height_ft=round(float(b.height_above_ground_ft), 2), rms_ft=round(float(b.rms_ft), 3),
            filled_pct=round(100.0 * filled / plan, 1), raw_plan_area_sqft=round(float(b.plan_area_sqft), 1)))
    if straighten:  # ON by default: straight shared sides, few vertices; falls back to the planes above (never worse)
        planes, borders = _straighten_with_borders(planes, region)
    else:
        borders = []
    if straighten:  # the envelope partition replaces planes and borders when its gate passes (planes_envelope)
        from .planes_envelope import envelope_planes
        env = envelope_planes(planes, {b.id: r for b, r in zip(blocks, raw, strict=True) if r is not None}, region)
        if env is not None:
            planes, borders = env
    return SnapResult(planes=planes, borders=borders, footprint_area_sqft=float(fp.area), raw_in_footprint_sqft=float(raw_in_fp),
                      bad_blocks=bad)


def snap_planes(blockset: BlockSet, footprint_polygon: Polygon | list[Any] | None = None, *,
                clip_to_footprint: bool, straighten: bool = True) -> list[Plane]:
    """The LiDAR planes of ``blockset`` made disjoint and gap-free.

    Each sloped or flat block is cleaned (``classify.clean_polygon``); an overlap goes to the larger plane; every
    uncovered part of the roof goes whole to the plane that dominates its border, or is cut at the middle between
    the planes it touches, or (an island) joins the nearest plane within 3 ft; pieces under 4 sq ft are dropped.
    A final tidy removes spikes and tiny edges, then ``planes_straight.straighten`` redraws the shared borders as
    straight lines with few vertices (unless ``straighten`` is False; it never makes a roof worse). With ``clip_to_footprint`` the planes are clipped to the footprint
    (the union then equals the footprint); without it (a footprint known to be a neighbour's or doubtful) they cover
    the union of the raw planes with its holes closed. ``footprint_polygon`` defaults to the block set's footprint.
    Returns ``[]`` for degenerate input; deterministic.
    """
    return snap_with_stats(blockset, footprint_polygon, clip_to_footprint=clip_to_footprint,
                           straighten=straighten).planes
