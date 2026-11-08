"""From LiDAR surface blocks to roof blocks (form, polygon, pitch) that tile the footprint.

WHY this layer exists: the segmentation (``blocks.py``) answers "which cells share a surface";
the model needs "which parts of the building are a hip, a gable, a shed awning or a flat roof".
Everything here is deterministic geometry plus a few thresholds named at the top, so the
Claude agent path (``agent.py``) can replace the decisions and keep the same tiling and
edge logic.

Input schema ``bond.roof_blocks/0.1`` is produced by ``blocks.py``; this module reads the JSON
(``BlockSet.load``) so the two sides only share the file format.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .skeleton import Pt, block_geometry, measure, open_ring, rect_fit, signed_area

log = logging.getLogger(__name__)

BLOCKS_SCHEMA = "bond.roof_blocks/0.1"

# Thresholds (feet / square feet / degrees). Named so tests and the README can cite them.
SHED_MAX_AREA_SQFT = 200.0  # a sloped block this small near the outline is an awning, not a roof
SHED_OUTLINE_DIST_FT = 1.5  # "touching the outline"
SHED_BELOW_FLAT_FT = 0.5  # and at least this far below the flat roof beside it
GROUP_GAP_FT = 1.5  # sloped blocks closer than this belong to one roof
ASPECT_MERGE_DEG = 25.0  # aspects closer than this are one slope direction
RECT_FIT_RATIO = 0.90  # union area / its rotated rectangle >= this: use the rectangle
RECT_FIT_RATIO_ROOF = 0.65  # hip/gable groups: faces lose their eave strip and corners to tree cells
RECT_INSIDE_RATIO = 0.75  # rectangle share inside the footprint to keep the full rectangle (stair-step outline becomes overhang)
FLAT_MERGE_STEP_FT = 0.5  # flat blocks closer in level than this may merge
WALL_STEP_FT = 1.0  # level difference that makes a wall (flat) or a step flashing (sloped)
GROUP_GROW_FT = 0.0  # grow hip/gable faces by this before fitting (eave strip dropped by the cell filter)
FACE_FILL_FACTOR = 1.0  # true roof area vs the measured faces (eave strip lost to the cell filter)
EXTEND_MAX_FT = 1.5  # a rectangle edge moves to a parallel footprint edge this close
LOW_SLOPE_RISE = 3.0  # an interior slope flatter than this is treated as flat roof
SPIKE_ANGLE_DEG = 10.0  # vertices sharper than this are spikes
MIN_EDGE_SQ_FT = 1.0  # edges shorter than this are dropped by the outline cleanup
MIN_CONTACT_FT = 8.0  # outline length a block must share to count as touching the outline
MIN_PIECE_SQFT = 3.0  # leftovers smaller than this are dropped after subtraction


# ----------------------------------------------------------------------------- data classes
@dataclass
class Block:
    """One LiDAR surface block (input). Polygon in model feet."""

    id: str
    kind: str  # flat | sloped
    polygon_ft: list[Pt]
    plan_area_sqft: float
    mean_z_ft: float
    height_above_ground_ft: float
    pitch_rise: float
    aspect_deg: float | None
    rms_ft: float = 0.0
    n_cells: int = 0

    @property
    def poly(self) -> Polygon:
        return Polygon(self.polygon_ft).buffer(0)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Block:
        return cls(id=str(d["id"]), kind=d["kind"], polygon_ft=open_ring(d["polygon_ft"]),
                   plan_area_sqft=float(d["plan_area_sqft"]), mean_z_ft=float(d.get("mean_z_ft", 0.0)),
                   height_above_ground_ft=float(d.get("height_above_ground_ft", d.get("mean_z_ft", 0.0))),
                   pitch_rise=float(d.get("pitch_rise") or 0.0),
                   aspect_deg=None if d.get("aspect_deg") is None else float(d["aspect_deg"]),
                   rms_ft=float(d.get("rms_ft") or 0.0), n_cells=int(d.get("n_cells") or 0))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "polygon_ft": [list(p) for p in self.polygon_ft],
                "plan_area_sqft": self.plan_area_sqft, "mean_z_ft": self.mean_z_ft,
                "height_above_ground_ft": self.height_above_ground_ft, "pitch_rise": self.pitch_rise,
                "aspect_deg": self.aspect_deg, "rms_ft": self.rms_ft, "n_cells": self.n_cells}


@dataclass
class BlockSet:
    """The ``bond.roof_blocks/0.1`` document."""

    address: dict[str, Any]
    origin: dict[str, float]
    frame: dict[str, Any]
    footprint_ft: list[Pt]
    footprint_meta: dict[str, Any] = field(default_factory=dict)
    lidar: dict[str, Any] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    borders: list[dict[str, Any]] = field(default_factory=list)
    outline_edges: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def footprint(self) -> Polygon:
        return Polygon(self.footprint_ft).buffer(0)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BlockSet:
        if d.get("schema") != BLOCKS_SCHEMA:
            raise ValueError(f"expected schema {BLOCKS_SCHEMA}, got {d.get('schema')!r}")
        return cls(address=d.get("address", {}), origin=d.get("origin", {"lat": 0.0, "lng": 0.0}),
                   frame=d.get("frame", {}), footprint_ft=open_ring(d["footprint_ft"]),
                   footprint_meta=d.get("footprint_meta", {}), lidar=d.get("lidar", {}),
                   blocks=[Block.from_dict(b) for b in d.get("blocks", [])], borders=d.get("borders", []),
                   outline_edges=d.get("outline_edges", []), extra=d.get("extra", {}))

    @classmethod
    def load(cls, path: str | Path) -> BlockSet:
        return cls.from_dict(json.loads(Path(path).read_text()))

    def to_dict(self) -> dict[str, Any]:
        ring = [list(p) for p in self.footprint_ft]
        return {"schema": BLOCKS_SCHEMA, "address": self.address, "origin": self.origin, "frame": self.frame,
                "footprint_ft": ring + [ring[0]], "footprint_meta": self.footprint_meta, "lidar": self.lidar,
                "blocks": [b.to_dict() for b in self.blocks], "borders": self.borders,
                "outline_edges": self.outline_edges, "extra": self.extra}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=1))


@dataclass
class RoofBlock:
    """One roof block of the output model (contract ``blocks[]``) plus build-time hints.

    ``level_ft`` is the absolute height of the flat roof, or of the eave of a sloped block;
    it is only used to type edges between blocks and is not written to the contract JSON.
    """

    id: str
    form: str  # flat | hip | gable | shed
    polygon: list[Pt]
    pitch_rise: float = 0.0
    aspect_deg: float | None = None  # shed only: downslope compass bearing
    gable_edges: list[int] = field(default_factory=list)
    level_ft: float | None = None
    eave_height_ft: float | None = None
    ridge_azimuth_deg: float | None = None
    source_blocks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    confidence: str = "medium"

    @property
    def poly(self) -> Polygon:
        return Polygon(self.polygon).buffer(0)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "form": self.form, "polygon": [list(p) for p in self.polygon],
                "pitch_rise": self.pitch_rise, "ridge_azimuth_deg": self.ridge_azimuth_deg,
                "gable_edges": list(self.gable_edges), "eave_height_ft": self.eave_height_ft,
                "plan_area_sqft": self.poly.area}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoofBlock:
        return cls(id=str(d["id"]), form=d["form"], polygon=norm_ring(d["polygon"]),
                   pitch_rise=float(d.get("pitch_rise") or 0.0),
                   aspect_deg=None if d.get("aspect_deg") is None else float(d["aspect_deg"]),
                   gable_edges=[int(i) for i in d.get("gable_edges", [])], level_ft=d.get("level_ft"),
                   eave_height_ft=d.get("eave_height_ft"), ridge_azimuth_deg=d.get("ridge_azimuth_deg"),
                   source_blocks=list(d.get("source_blocks", [])), notes=list(d.get("notes", [])),
                   confidence=d.get("confidence", "medium"))


@dataclass
class Classification:
    """Roof blocks plus what the build learned (feeds the model's confidence and warnings)."""

    blocks: list[RoofBlock]
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gap_filled_pct: float = 0.0
    uncovered_pct: float = 0.0  # share of the roof outline still uncovered after gap fill
    fitted_area_sqft: float = 0.0  # area of the fitted blocks before any gap fill
    method: str = "lidar_skeleton"


# ----------------------------------------------------------------------------- geometry utils
def norm_ring(polygon: list[Any]) -> list[Pt]:
    """Open CCW ring with collinear points removed."""
    pts = open_ring(polygon)
    if signed_area(pts) < 0:
        pts = pts[::-1]
    poly = Polygon(pts).buffer(0)
    if poly.is_empty:
        return pts
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)
    return ring_of(poly)


def ring_of(poly: Polygon, simplify: float = 1e-6) -> list[Pt]:
    """Exterior ring of ``poly`` as an open CCW list with collinear vertices dropped."""
    poly = orient(poly, 1.0)
    p = poly.simplify(simplify, preserve_topology=True) if simplify else poly
    if p.is_empty or not isinstance(p, Polygon):
        p = poly
    return [(float(x), float(y)) for x, y in list(p.exterior.coords)[:-1]]


def polygons_of(geom: BaseGeometry) -> list[Polygon]:
    """All polygon parts of any geometry."""
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [g for part in getattr(geom, "geoms", []) for g in polygons_of(part)]


def largest(geom: BaseGeometry) -> Polygon | None:
    parts = polygons_of(geom)
    return max(parts, key=lambda g: g.area) if parts else None


def _densify(poly: Polygon, spacing: float) -> list[Pt]:
    out: list[Pt] = []
    for ring in [poly.exterior, *poly.interiors]:
        n = max(2, int(ring.length / spacing))
        out.extend((ring.interpolate(i / n, normalized=True).x, ring.interpolate(i / n, normalized=True).y)
                   for i in range(n))
    return out


def tile_to_footprint(polys: dict[str, Polygon], footprint: Polygon, keep_outside: set[str] | None = None,
                      spacing: float = 1.0, fillers: set[str] | None = None) -> tuple[dict[str, Polygon], float]:
    """Give every footprint area no block covers to the nearest block (Voronoi on the outlines).

    WHY Voronoi on densified outlines: it makes straight bisector edges shared exactly by the two
    neighbours (no slivers or overlaps), unlike a raster assignment. ``keep_outside`` ids may
    extend beyond the footprint (awnings); every other block is clipped to it. When ``fillers``
    is given only those ids receive gap area (the rest keep their polygon unchanged).
    Returns the new polygons and the fraction of the footprint that was filled.
    """
    keep_outside = keep_outside or set()
    clipped: dict[str, Polygon] = {}
    for k, p in polys.items():
        q = p if k in keep_outside else largest(p.intersection(footprint))
        if q is not None and not q.is_empty and q.area > 0:
            clipped[k] = q
    if not clipped:
        return clipped, 0.0
    gap = footprint.difference(unary_union(list(clipped.values())))
    gap_area = gap.area
    if gap_area < 0.5:
        return clipped, 0.0
    pts: list[Point] = []
    labels: list[str] = []
    seen: set[tuple[int, int]] = set()
    takers = {k for k in clipped if not fillers or k in fillers} or set(clipped)
    for k, p in clipped.items():
        if k not in takers:
            continue
        for x, y in _densify(p, spacing):
            key = (round(x * 100), round(y * 100))  # coincident points break the Voronoi union
            if key in seen:
                continue
            seen.add(key)
            pts.append(Point(x, y))
            labels.append(k)
    minx, miny, maxx, maxy = footprint.bounds
    env = shapely.geometry.box(minx - 100, miny - 100, maxx + 100, maxy + 100)
    cells = list(shapely.voronoi_polygons(MultiPoint(pts), extend_to=env).geoms)
    tree = STRtree(pts)
    owned: dict[str, list[BaseGeometry]] = {k: [] for k in takers}
    for cell in (c for raw in cells for c in polygons_of(shapely.make_valid(raw))):
        idx = tree.query(cell, predicate="contains")
        if len(idx):
            owned[labels[int(idx[0])]].append(cell)
    out: dict[str, Polygon] = {}
    for k, p in clipped.items():
        if k not in takers:
            out[k] = p
            continue
        share = _safe_union(owned[k]).intersection(gap) if owned[k] else Polygon()
        merged = unary_union([p, share]).buffer(0)
        if k not in keep_outside:
            merged = merged.intersection(footprint)
        best = largest(merged)
        out[k] = best.simplify(0.1, preserve_topology=True) if best is not None else p
    return out, gap_area / footprint.area


def _safe_union(geoms: list[BaseGeometry]) -> BaseGeometry:
    """Union that survives GEOS topology errors on near-degenerate Voronoi cells."""
    try:
        return unary_union(geoms)
    except shapely.errors.GEOSException:
        return unary_union([shapely.set_precision(g, 1e-6) for g in geoms])


def _bearing(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, dy)) % 360


def _ang_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two compass bearings."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def cluster_aspects(items: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge (aspect, weight) pairs closer than ``ASPECT_MERGE_DEG``; returns (centre, weight)."""
    clusters: list[list[tuple[float, float]]] = []
    for a, w in sorted(items):
        for c in clusters:
            if _ang_diff(a, c[0][0]) <= ASPECT_MERGE_DEG:
                c.append((a, w))
                break
        else:
            clusters.append([(a, w)])
    out = []
    for c in clusters:
        wt = sum(w for _, w in c) or 1.0
        x = sum(math.sin(math.radians(a)) * w for a, w in c)
        y = sum(math.cos(math.radians(a)) * w for a, w in c)
        out.append((_bearing(x, y), wt))
    return out


def decide_form(aspects: list[tuple[float, float]]) -> tuple[str, list[str]]:
    """Roof form from the distinct slope directions of one connected sloped cluster."""
    cl = cluster_aspects(aspects)
    k = len(cl)
    if k <= 1:
        return "shed", []
    if k == 2:
        if abs(_ang_diff(cl[0][0], cl[1][0]) - 180) <= 35:
            return "gable", []
        return "hip", [f"Two slope directions {_ang_diff(cl[0][0], cl[1][0]):.0f} deg apart; treated as a hip corner."]
    if k == 4:
        ordered = sorted(c[0] for c in cl)
        gaps = [(ordered[(i + 1) % 4] - ordered[i]) % 360 for i in range(4)]
        if all(abs(g - 90) <= 35 for g in gaps):
            return "hip", []
        return "hip", ["Four slope directions are not 90 deg apart; treated as a hip."]
    return "hip", [f"{k} slope directions; complex roof treated as one hip block (low confidence)."]


def gable_edge_indices(ring: list[Pt], aspect_deg: float, tol: float = 30.0) -> list[int]:
    """The (up to) two longest polygon edges whose outward normal is perpendicular to the slope.

    WHY only two: a ragged outline has many short edges facing the right way; treating each as a
    gable end makes the skeleton fail, and a gable roof has exactly two ends.
    """
    cand = [e for e in measure(ring)["edges"]
            if abs(_ang_diff(e["outward_bearing_deg"], aspect_deg) - 90) <= tol]
    cand.sort(key=lambda e: -e["length_ft"])
    longest = cand[0]["length_ft"] if cand else 0.0
    keep = [e for e in cand if e["length_ft"] >= 0.25 * longest][:2]
    return sorted(int(e["index"]) for e in keep)


def ridge_azimuth(form: str, ring: list[Pt], aspect_deg: float | None, geom: dict[str, Any] | None) -> float | None:
    """Compass bearing (0..180) of the ridge line; None for flat roofs."""
    if form == "flat":
        return None
    if form == "shed" and aspect_deg is not None:
        return (aspect_deg + 90) % 180
    if geom:
        ridges = [e for e in geom["edges"] if e["type"] == "ridge"]
        if ridges:
            r = max(ridges, key=lambda e: e["plan_length"])
            (x1, y1, _), (x2, y2, _) = r["polyline_xyz"]
            return _bearing(x2 - x1, y2 - y1) % 180
    c, _, _, _ = rect_fit(ring)
    a, b = (c[0], c[1]) if math.dist(c[0], c[1]) >= math.dist(c[1], c[2]) else (c[1], c[2])
    return _bearing(b[0] - a[0], b[1] - a[1]) % 180


# ----------------------------------------------------------------------------- levels
def assign_levels(roof_blocks: list[RoofBlock], blockset: BlockSet) -> None:
    """Fill ``level_ft`` and ``eave_height_ft`` from the LiDAR blocks under each roof block.

    WHY: edge typing needs to know whether a neighbour is higher (wall / step flashing) or at
    the same level (eave). A sloped block's level is its EAVE, found by subtracting the
    skeleton's mean surface height above the eave from the measured mean z of its faces.
    Roof blocks with no LiDAR under them (synthetic fixtures) get level 0.
    """
    for rb in roof_blocks:
        if rb.level_ft is not None and rb.eave_height_ft is not None:
            continue
        want_flat = rb.form == "flat"
        poly = rb.poly
        sumw = sumz = sumh = 0.0
        for b in blockset.blocks:
            if (b.kind == "flat") != want_flat:
                continue
            w = poly.intersection(b.poly).area
            if w < 5.0:
                continue
            sumw += w
            sumz += w * b.mean_z_ft
            sumh += w * (b.mean_z_ft - b.height_above_ground_ft)
        if sumw == 0:
            if rb.level_ft is None:
                rb.level_ft = 0.0
            if rb.eave_height_ft is None:
                rb.eave_height_ft = 0.0
            continue
        mean_z, ground = sumz / sumw, sumh / sumw
        rise = 0.0
        if rb.form != "flat":
            geom = block_geometry(rb.form, rb.polygon, rb.pitch_rise, rb.gable_edges, rb.aspect_deg)
            tot = sum(f["plan_area"] for f in geom["facets"]) or 1.0
            rise = sum(f["plan_area"] * _plane_at(f["plane"], *Polygon(f["polygon_xy"]).centroid.coords[0])
                       for f in geom["facets"]) / tot
        if rb.level_ft is None:
            rb.level_ft = mean_z - rise
        if rb.eave_height_ft is None:
            rb.eave_height_ft = rb.level_ft - ground


def _plane_at(plane: tuple[float, float, float], x: float, y: float) -> float:
    return plane[0] + plane[1] * x + plane[2] * y


# ----------------------------------------------------------------------------- classification
def _components(n: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in pairs:
        parent[find(a)] = find(b)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def classify_blocks(blockset: BlockSet, *, merge_flats: bool = False,
                    merge_flat_step_ft: float = FLAT_MERGE_STEP_FT) -> Classification:
    """Deterministic roof blocks from LiDAR blocks (method ``lidar_skeleton``).

    Steps: (d) awnings -> (a) group sloped faces into roofs -> tile the footprint ->
    fit rectangles -> (b) flats from the tiled remainder, merged when the level step is small
    and the union stays one simple polygon.
    """
    fp = blockset.footprint
    res = Classification(blocks=[])
    blocks = [b for b in blockset.blocks if not b.poly.is_empty and b.poly.area > 1.0]
    # Roofs overhang the county wall line, so blocks may extend past the footprint: the roof outline
    # is the footprint plus the blocks, never the footprint alone.
    outline = unary_union([fp] + [b.poly for b in blocks]).buffer(0.01).buffer(-0.01)
    flats = [b for b in blocks if b.kind == "flat"]
    sloped = [b for b in blocks if b.kind != "flat"]
    low = [b for b in sloped if b.pitch_rise < LOW_SLOPE_RISE and _contact_ft(b.poly, fp) < MIN_CONTACT_FT]
    for b in low:  # its area goes to the surrounding flat through the gap fill
        c = b.poly.centroid
        res.notes.append(f"Low-slope area inside the flat roof at ({c.x:.0f}, {c.y:.0f}) ft, pitch "
                         f"{b.pitch_rise:.1f}/12, treated as flat; verify.")
    sloped = [b for b in sloped if b not in low]

    def flat_level_near(p: Polygon) -> float | None:
        if not flats:
            return None
        nearest = min(flats, key=lambda f: f.poly.distance(p))
        return nearest.mean_z_ft

    # (d) awnings: small, low, touching the outline
    sheds: list[Block] = []
    roofs: list[Block] = []
    for b in sloped:
        p = b.poly
        lvl = flat_level_near(p)
        touching = _contact_ft(p, fp) >= MIN_CONTACT_FT
        if (b.plan_area_sqft < SHED_MAX_AREA_SQFT and touching and lvl is not None
                and b.mean_z_ft < lvl - SHED_BELOW_FLAT_FT):
            sheds.append(b)
        else:
            roofs.append(b)

    # (a) group connected sloped faces: LiDAR borders plus proximity
    index = {b.id: i for i, b in enumerate(roofs)}
    pairs = [(index[x["a"]], index[x["b"]]) for x in blockset.borders if x["a"] in index and x["b"] in index]
    for i in range(len(roofs)):
        for j in range(i + 1, len(roofs)):
            if roofs[i].poly.distance(roofs[j].poly) <= GROUP_GAP_FT:
                pairs.append((i, j))
    groups = [[roofs[i] for i in g] for g in _components(len(roofs), pairs)]

    # priority when blocks overlap: sloped > awnings > flats
    sloped_union = unary_union([b.poly for b in roofs + sheds]) if (roofs or sheds) else Polygon()
    polys: dict[str, Polygon] = {}
    for b in roofs + sheds:
        polys[b.id] = b.poly
    claimed: BaseGeometry = Polygon()  # flats must not overlap each other either (Solar boxes do)
    for b in flats:
        q = b.poly.difference(sloped_union).difference(claimed)
        part = largest(q)
        if part is not None and part.area >= MIN_PIECE_SQFT:
            polys[b.id] = part
            claimed = claimed.union(part)
    # First tile: gives awnings and single-face slopes their outline-snapped polygon. Hip and gable
    # groups are NOT taken from it: gap cells beside them (tree cover) must not become roof.
    tiled, _ = tile_to_footprint(polys, outline, keep_outside={b.id for b in sheds})

    final: list[RoofBlock] = []
    taken: list[Polygon] = []
    # sloped groups (largest first)
    ordered = sorted(groups, key=lambda g: -sum(b.plan_area_sqft for b in g))
    for g in ordered:
        if len(g) >= 2:  # faces as measured, grown by the eave strip the cell filter dropped
            part = largest(unary_union([b.poly for b in g]).buffer(GROUP_GROW_FT).buffer(0))
        else:
            part = largest(unary_union([tiled[b.id] for b in g if b.id in tiled]).buffer(0))
        if part is None:
            continue
        weights = [(b.aspect_deg if b.aspect_deg is not None else 180.0, b.plan_area_sqft) for b in g]
        form, notes = decide_form(weights)
        wsum = sum(b.plan_area_sqft for b in g) or 1.0
        pitch = sum(b.pitch_rise * b.plan_area_sqft for b in g) / wsum
        if form == "shed" and pitch < 3.0:
            notes.append("Low-slope section under 3/12 (ramp, drainage or equipment?); kept as a shed, verify.")
        ring, extra = _fit_ring(part, outline, notes,
                                ratio=RECT_FIT_RATIO_ROOF if form in ("hip", "gable") else RECT_FIT_RATIO)
        if len(g) >= 2 and len(ring) == 4:
            ring, shrunk = _match_area(ring, part.area * FACE_FILL_FACTOR)
            if shrunk:
                extra.append("Rectangle scaled to the measured face area: faces fill the roof, so a rectangle "
                             "larger than their union (ragged corners) overstates it.")
            ring, moved = _extend_to_outline(ring, fp)
            if moved:
                extra.append(f"{moved} rectangle edge(s) moved to the parallel footprint edge within {EXTEND_MAX_FT} ft.")
        aspect = cluster_aspects(weights)[0][0] if form in ("shed", "gable") else None
        gable: list[int] = []
        if form == "gable":
            gable = gable_edge_indices(ring, aspect if aspect is not None else 0.0)
            if len(gable) < 2:
                notes.append("Gable ends not found on the block outline; fell back to a hip.")
                form, gable = "hip", []
        try:
            geom = block_geometry(form, ring, pitch, gable, aspect)
        except ValueError as exc:  # skeleton refused the outline: fall back to its rectangle as a hip
            log.warning("skeleton failed (%s); using the rectangle", exc)
            ring = rect_fit(ring)[0]
            form, gable = "hip", []
            notes.append("Outline too ragged for a skeleton; replaced by its rectangle.")
            geom = block_geometry(form, ring, pitch, gable, aspect)
        rb = RoofBlock(id="", form=form, polygon=ring, pitch_rise=pitch, aspect_deg=aspect, gable_edges=gable,
                       ridge_azimuth_deg=ridge_azimuth(form, ring, aspect, geom),
                       source_blocks=[b.id for b in g], notes=notes + extra,
                       confidence="medium" if len(notes) + len(extra) else "high")
        final.append(rb)
        taken.append(Polygon(ring))
        res.notes.extend(f"{form.capitalize()} block from {len(g)} LiDAR face(s): {n}" for n in notes)
    # awnings
    for b in sorted(sheds, key=lambda s: -s.plan_area_sqft):
        ring = _awning_rect(b.poly, fp)
        extra = ["Awning fitted to a rectangle along the outline edge it touches."]
        aspect = b.aspect_deg if b.aspect_deg is not None else 180.0
        geom = block_geometry("shed", ring, b.pitch_rise, [], aspect)
        final.append(RoofBlock(id="", form="shed", polygon=ring, pitch_rise=b.pitch_rise, aspect_deg=aspect,
                               ridge_azimuth_deg=ridge_azimuth("shed", ring, aspect, geom),
                               source_blocks=[b.id], notes=["Small low slope on the outline: awning."] + extra,
                               confidence="low"))
        taken.append(Polygon(ring))
    # flats: measured polygons minus everything placed, then the footprint gaps go to the flats
    placed = unary_union(taken) if taken else Polygon()
    second: dict[str, Polygon] = {f"_r{i}": Polygon(r.polygon) for i, r in enumerate(final)}
    flat_ids: list[str] = []  # block order, not a set: merge results must not depend on hash order
    meta: dict[str, Block] = {}
    for b in flats:
        if b.id not in polys:
            continue
        part = largest(polys[b.id].difference(placed))
        if part is not None and part.area >= MIN_PIECE_SQFT:
            second[b.id] = part
            flat_ids.append(b.id)
            meta[b.id] = b
    tiled2, gap = tile_to_footprint(second, outline, keep_outside={f"_r{i}" for i, r in enumerate(final)
                                                              if r.form == "shed"}, fillers=set(flat_ids))
    res.gap_filled_pct = 100.0 * gap
    res.fitted_area_sqft = unary_union([b.poly for b in blocks if b not in low]).area
    flat_pieces: list[tuple[Polygon, list[str], float, float]] = []
    for fid in flat_ids:
        b = meta[fid]
        for piece in polygons_of(tiled2[fid].difference(placed)):
            if piece.area >= MIN_PIECE_SQFT:
                flat_pieces.append((piece, [b.id], b.mean_z_ft, b.mean_z_ft - b.height_above_ground_ft))
    if merge_flats:
        flat_pieces = _merge_flats(flat_pieces, merge_flat_step_ft, res)
    for piece, ids, _, _ in sorted(flat_pieces, key=lambda t: -t[0].area):
        pp = clean_polygon(piece)
        if pp is None or pp.area < MIN_PIECE_SQFT:
            continue
        final.append(RoofBlock(id="", form="flat", polygon=ring_of(pp), level_ft=None, source_blocks=ids,
                               confidence="medium"))
    covered = unary_union([Polygon(r.polygon) for r in final]).intersection(outline).area if final else 0.0
    left = 1.0 - covered / outline.area if outline.area else 0.0
    res.uncovered_pct = 100.0 * max(left, 0.0)
    if res.gap_filled_pct >= 0.5 or res.uncovered_pct > 1.0:
        res.notes.append(f"{res.gap_filled_pct:.1f}% of the footprint had no LiDAR-fitted block before gap fill "
                         "(tree cover, dropped edge cells); it was assigned to the nearest flat block. "
                         f"{res.uncovered_pct:.1f}% remains uncovered after gap fill.")
        log.info("gap fill: %.1f%% assigned, %.1f%% uncovered", res.gap_filled_pct, res.uncovered_pct)
    for i, rb in enumerate(final, start=1):
        rb.id = f"b{i}"
    assign_levels(final, blockset)
    res.blocks = final
    return res


def _contact_ft(p: Polygon, fp: Polygon) -> float:
    """Length of footprint outline within 1.5 ft of ``p`` (a corner brush is not 'touching')."""
    return fp.exterior.intersection(p.buffer(SHED_OUTLINE_DIST_FT)).length


def _awning_rect(poly: Polygon, fp: Polygon) -> list[Pt]:
    """Rectangle for an awning: one axis along the footprint edge it touches, outer side on the outline.

    The outer side is the farther of the measured extent (which includes the overhang) and the
    outline, so the awning always reaches the wall line and no flat sliver is left outside it.
    """
    best, best_ov = None, 0.0
    for p, q in zip(fp.exterior.coords[:-1], fp.exterior.coords[1:], strict=False):
        seg = LineString([p, q])
        if seg.distance(poly) > SHED_OUTLINE_DIST_FT + 1.0:
            continue
        ov = seg.intersection(poly.buffer(2.5)).length
        if ov > best_ov:
            best, best_ov = (p, q), ov
    if best is None:
        return rect_fit(ring_of(poly, 0.0))[0]
    (px, py), (qx, qy) = best
    L = math.dist((px, py), (qx, qy))
    ux, uy = (qx - px) / L, (qy - py) / L
    nx, ny = uy, -ux
    c = poly.centroid
    if ((px + qx) / 2 - c.x) * nx + ((py + qy) / 2 - c.y) * ny < 0:
        nx, ny = -nx, -ny
    pts = list(poly.exterior.coords)
    ss = [x * ux + y * uy for x, y in pts]
    tt = [x * nx + y * ny for x, y in pts]
    t_out = max(max(tt), px * nx + py * ny)
    s0, s1, t0 = min(ss), max(ss), min(tt)
    corners = [(s0, t0), (s1, t0), (s1, t_out), (s0, t_out)]
    ring = [(s * ux + t * nx, s * uy + t * ny) for s, t in corners]
    return ring if signed_area(ring) > 0 else ring[::-1]


def clean_polygon(poly: Polygon) -> Polygon:
    """Remove spikes and stubs: drop vertices sharper than 10 deg or making edges under 1 ft, simplify 0.3 ft."""
    p = largest(poly.buffer(0))
    if p is None:
        return poly
    pts = ring_of(p, 0.0)
    changed = True
    while changed and len(pts) > 3:
        changed = False
        n = len(pts)
        for i in range(n):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
            v1 = (a[0] - b[0], a[1] - b[1])
            v2 = (c[0] - b[0], c[1] - b[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if min(l1, l2) < 1e-9:
                ang = 0.0
            else:
                ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))))
            if ang < SPIKE_ANGLE_DEG or min(l1, l2) < MIN_EDGE_SQ_FT:
                pts.pop(i)
                changed = True
                break
    q = Polygon(pts).buffer(0)
    q = largest(q.simplify(0.3, preserve_topology=True)) if not q.is_empty else None
    return q if q is not None and q.area > 0 else p


def _match_area(ring: list[Pt], target: float) -> tuple[list[Pt], bool]:
    """Scale a rectangle about its centre down to ``target`` area (never up)."""
    area = Polygon(ring).area
    if area <= target * 1.02:
        return ring, False
    k = math.sqrt(target / area)
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in ring], True


def _extend_to_outline(ring: list[Pt], fp: Polygon) -> tuple[list[Pt], int]:
    """Move each edge of a rectangle onto a parallel footprint edge within ``EXTEND_MAX_FT``.

    WHY: faces as measured stop short of the eave; the true roof edge is the wall line (plus
    overhang) where the footprint has an edge parallel to ours. Never moves an edge inward.
    """
    n = len(ring)
    segs = list(zip(fp.exterior.coords[:-1], fp.exterior.coords[1:], strict=False))
    lines = []
    moved = 0
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = uy, -ux  # outward normal of a CCW ring
        best = 0.0
        for p, q in segs:
            sl = math.dist(p, q)
            if sl < 0.5 * L:
                continue
            dx, dy = (q[0] - p[0]) / sl, (q[1] - p[1]) / sl
            if abs(dx * uy - dy * ux) > math.sin(math.radians(6)):
                continue
            mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
            d = (mx - a[0]) * nx + (my - a[1]) * ny  # signed offset along the outward normal
            if 0.05 < d <= EXTEND_MAX_FT and d > best:
                best = d
        moved += best > 0
        lines.append(((a[0] + nx * best, a[1] + ny * best), (b[0] + nx * best, b[1] + ny * best)))
    out = []
    for i in range(n):
        pt = _isect(*lines[i - 1], *lines[i])
        out.append(pt if pt else ring[i])
    return out, moved


def _isect(a: Pt, b: Pt, c: Pt, d: Pt) -> Pt | None:
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    return (a[0] + t * r[0], a[1] + t * r[1])


def _fit_ring(part: Polygon, fp: Polygon, notes: list[str], allow_outside: bool = False,
              ratio: float = RECT_FIT_RATIO) -> tuple[list[Pt], list[str]]:
    """Rotated rectangle when the polygon is within 10% of it, else the simplified polygon.

    WHY: the skeleton of a ragged outline invents hips and valleys from sub-2-ft jogs; a roof
    that is close to a rectangle should be treated as one. A rectangle that leaves the
    footprint by more than 3% is clipped to it instead.
    """
    extra: list[str] = []
    rect, _, _, rarea = rect_fit(ring_of(part, 0.0))
    if part.area / rarea >= ratio:
        rp = Polygon(rect)
        if allow_outside or rp.intersection(fp).area / rarea >= RECT_INSIDE_RATIO:
            return rect, extra
        clipped = largest(rp.intersection(fp))
        if clipped is not None:
            extra.append("Rectangle clipped to the footprint.")
            return ring_of(clipped.simplify(0.2, preserve_topology=True)), extra
    extra.append(f"Outline is {100 * part.area / rarea:.0f}% of its rectangle; kept as a simplified polygon.")
    return ring_of(part.simplify(0.4, preserve_topology=True)), extra


def _merge_flats(pieces: list[tuple[Polygon, list[str], float, float]], step: float,
                 res: Classification) -> list[tuple[Polygon, list[str], float, float]]:
    """Greedy merge of touching flat pieces whose levels differ by < ``step`` ft.

    Only merges that stay one simple polygon (no holes, one part): report keeps non-simple
    combinations separate and draws the shared line as an eave.
    """
    pieces = list(pieces)
    merged_any = True
    kept_separate = 0
    while merged_any:
        merged_any = False
        best: tuple[int, int, Polygon] | None = None
        for i in range(len(pieces)):
            for j in range(i + 1, len(pieces)):
                pi, pj = pieces[i], pieces[j]
                if abs(pi[2] - pj[2]) >= step:
                    continue
                if pi[0].distance(pj[0]) > 0.3 or pi[0].buffer(0.15).intersection(pj[0]).length < 2.0:
                    continue
                u = unary_union([pi[0].buffer(0.05), pj[0].buffer(0.05)]).buffer(-0.05)
                if isinstance(u, Polygon) and not u.interiors:
                    best = (i, j, u)
                    break
                kept_separate += 1
            if best:
                break
        if best:
            i, j, u = best
            a, b = pieces[i], pieces[j]
            w = a[0].area + b[0].area
            z = (a[2] * a[0].area + b[2] * b[0].area) / w
            g = (a[3] * a[0].area + b[3] * b[0].area) / w
            pieces = [p for k, p in enumerate(pieces) if k not in (i, j)] + [(u, a[1] + b[1], z, g)]
            merged_any = True
    if kept_separate:
        res.notes.append(f"{kept_separate} flat-to-flat joins kept separate because the union was not one simple polygon.")
    return pieces


def build_roof_blocks(blockset: BlockSet, **kw: Any) -> list[RoofBlock]:
    """Contract entry point: roof blocks for ``blockset`` (see :func:`classify_blocks`)."""
    return classify_blocks(blockset, **kw).blocks



def complete_tiling(blocks: list[RoofBlock], blockset: BlockSet, min_flat_sqft: float = 150.0
                    ) -> tuple[list[RoofBlock], float, list[str]]:
    """Make agent-proposed blocks tile the footprint (same rules as the deterministic path).

    Sloped and awning blocks win overlaps; footprint area nobody claimed becomes new flat blocks
    when a connected piece is at least ``min_flat_sqft`` (the agent need not list flat roofs);
    smaller leftovers go to the nearest block. Returns ``(blocks, filled_pct, notes)``.
    """
    fp = blockset.footprint
    notes: list[str] = []
    for i, b in enumerate(blocks):  # temporary unique ids; final ids b1.. are set at the end
        b.id = f"a{i}"
    sloped = [b for b in blocks if b.form != "flat"]
    sloped_union = unary_union([b.poly for b in sloped]) if sloped else Polygon()
    polys: dict[str, Polygon] = {}
    kept: list[RoofBlock] = []
    claimed: BaseGeometry = Polygon()
    for b in sorted(blocks, key=lambda x: x.form == "flat"):  # sloped first
        p = b.poly if b.form != "flat" else largest(b.poly.difference(sloped_union).difference(claimed))
        if p is None or p.area < MIN_PIECE_SQFT:
            continue
        if b.form == "flat":
            claimed = claimed.union(p)
        polys[b.id] = p
        kept.append(b)
    taken = unary_union(list(polys.values())) if polys else Polygon()
    remainder = fp.difference(taken)
    filled_big = 0.0
    for piece in polygons_of(remainder):
        if piece.area >= min_flat_sqft:
            nb = RoofBlock(id=f"x{len(polys)}", form="flat", polygon=ring_of(piece.simplify(0.1)),
                           notes=["Flat remainder of the footprint added by the harness."])
            polys[nb.id] = piece
            kept.append(nb)
            filled_big += piece.area
    tiled, gap = tile_to_footprint(polys, fp, keep_outside={b.id for b in kept if b.form == "shed"})
    for b in kept:
        if b.id in tiled:
            b.polygon = ring_of(clean_polygon(tiled[b.id]) if b.form == "flat" else tiled[b.id], 0.05)
    pct = 100.0 * (gap + filled_big / fp.area)
    if filled_big:
        notes.append(f"{100.0 * filled_big / fp.area:.1f}% of the footprint was left unclaimed and became flat "
                     "block(s).")
    if gap >= 0.005:
        notes.append(f"{100.0 * gap:.1f}% of the footprint was in small gaps and went to the nearest block.")
    for i, b in enumerate(sorted(kept, key=lambda x: (x.form == "flat", x.form == "shed", -x.poly.area)), start=1):
        b.id = f"b{i}"
    return sorted(kept, key=lambda b: int(b.id[1:])), pct, notes
