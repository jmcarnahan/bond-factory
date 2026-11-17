"""Roof planes partitioned by their plane equations: each roof section is the lower envelope of its planes (internal).

``envelope_planes(planes, raw, region)`` takes the snapped, tiled planes (``planes.Plane`` with ``plane_eq`` on one
height datum), the raw LiDAR cluster of each (by id, inside the outline; None = from ``Plane.raw_polygon``) and the
outline, and redraws the borders from geometry instead of from where the clusters happen to stop:

1. Facings within 10 degrees of a building axis are set onto it (``c`` re-fitted to keep the mean height); parallel
   planes of one face (a slope split by solar panels) get one equation.
2. Sections: neighbours that meet in height along their border (or whose intersection line cleanly separates their
   clusters where they meet) are one section; borders between sections are wall steps, redrawn as straight axis
   lines (or one L); a section inside another (a dormer) is the axis box of its cluster (planes_envelope_lines).
3. Inside a section the intersection lines of neighbouring planes (turned onto an axis or a diagonal within 8
   degrees), straight step lines and splits between clusters of one face cut it into cells. A line that separates
   two clusters where they meet also says which side each plane may be on there (this is what makes valleys come
   out right). A cell well covered by raw clusters goes to the plane whose cluster covers most of it, any other cell
   to the LOWEST nearby plane allowed there (a pitched roof is the lower envelope of its planes). When that disagrees
   with the clusters too much, or a plane is starved even after its cluster's box is added, the section falls back
   to the clusters alone ("arrangement") (planes_envelope_cells).
4. Small, thin and detached pieces join a neighbour; near vertices are welded and collinear ones dropped
   (planes_envelope_clean); shared borders are classified ridge, hip, valley, step or seam.

It never makes a roof worse: the result must pass ``planes_envelope_gate.gate`` or the function returns None and the
caller keeps its own planes. Pure shapely, deterministic, never raises.
"""

from __future__ import annotations

import dataclasses
import logging
import math
from dataclasses import dataclass, field
from typing import Any

from shapely import set_precision
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .classify import polygons_of
from .planes_envelope_cells import (
    NEAR_FT,
    borders,
)
from .planes_envelope_clean import (
    collapse_junction_edges,
    drop_collinear,
    node_rings,
    rehome_detached,
    thin_strips,
    weld,
)
from .planes_envelope_gate import LOSE_OK_SQFT, gate
from .planes_envelope_geom import Eq, aspect_of, axis_deg, eq_of, square_eq, z_at
from .planes_envelope_lines import (
    MIN_GRAD_DIFF,
    neighbours,
    sections,
)
from .planes_envelope_split import partition, sub_regions, subsections
from .planes_envelope_steps import section_regions

log = logging.getLogger("roof_measure.planes")

GRID = 0.01
JUNCTION_FT = 2.5  # a border shorter than this between two junctions closes into one junction
WELD_FT = 0.5  # vertices closer than this become one (an edge this short inside the roof is a stub)
SPLIT_WELD_FT = 1.0  # ... on the split retry (a big roof: its many step lines leave jogs under a foot)
SAME_FACE_FT = 0.5  # parallel planes this close in height over their clusters are one roof face
SPLIT_MIN_PLANES = 8  # retry: a section with more planes than this is partitioned part by part (planes_envelope_split)


@dataclass
class EnvelopeResult:
    """Everything the envelope step knows; ``gate_failure`` None means ``planes`` and ``borders`` are good."""

    planes: list[Any] = field(default_factory=list)
    borders: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)  # {section, planes, method}
    moves: dict[str, dict[str, Any]] = field(default_factory=dict)  # per plane: turn_deg, max_dz_ft
    merged_small: list[str] = field(default_factory=list)
    gate_failure: str | None = "not run"
    lines: list[dict[str, Any]] = field(default_factory=list)  # debug: the roof lines tried per pair (indices)
    steps: str = "square"  # "legacy" when the square step lines failed the gate and the older ones passed
    refused: str | None = None  # ... and why the square ones were refused


def _finish_polys(polys: list[BaseGeometry], outline: BaseGeometry, weld_ft: float = WELD_FT) -> list[BaseGeometry]:
    """Collinear vertices out, vertices closer than ``WELD_FT`` welded (no stub edge inside the roof), 0.01 ft grid."""
    clean = [p if isinstance(p, Polygon) else Polygon() for p in polys]
    live = [k for k, p in enumerate(clean) if not p.is_empty]
    fixed = weld(drop_collinear([orient(clean[k], 1.0) for k in live]), outline, weld_ft)
    fixed = drop_collinear(collapse_junction_edges(drop_collinear(fixed), outline, JUNCTION_FT))
    fixed = node_rings(fixed)  # a roof line ending on another plane's edge (a T) puts its end point on that edge too
    out: list[BaseGeometry] = [Polygon()] * len(polys)
    for k, g in zip(live, fixed, strict=True):
        q = set_precision(g, GRID)
        out[k] = q if isinstance(q, Polygon) and q.is_valid and not q.is_empty else g
    return out


def _one_face(planes: list[Any], raws: list[BaseGeometry], shapes: list[BaseGeometry], eqs: list[Eq],
              res: EnvelopeResult) -> None:
    """Parallel planes whose clusters lie near each other and agree in height between them (median gap under
    ``SAME_FACE_FT`` over both clusters) are one roof face split by an obstacle (solar panels, a vent): they get one
    equation, the area-weighted mean of theirs, so their ridges and valleys line up."""
    n = len(planes)
    for i in range(n):
        for j in range(i + 1, n):
            ri = raws[i] if not raws[i].is_empty else shapes[i]
            rj = raws[j] if not raws[j].is_empty else shapes[j]
            gi, gj = eqs[i], eqs[j]
            if math.hypot(gi[0] - gj[0], gi[1] - gj[1]) >= MIN_GRAD_DIFF or ri.distance(rj) > NEAR_FT:
                continue
            both = unary_union([ri, rj])
            pts = [(q[0], q[1]) for g in polygons_of(both) for q in g.exterior.coords]
            gaps = sorted(abs(z_at(gi, x, y) - z_at(gj, x, y)) for x, y in pts)
            if not gaps or gaps[len(gaps) // 2] > SAME_FACE_FT:
                continue
            wi, wj = max(ri.area, 1e-6), max(rj.area, 1e-6)
            mean = tuple((wi * a + wj * b) / (wi + wj) for a, b in zip(gi, gj, strict=True))
            for k, r in ((i, ri), (j, rj)):
                c = r.centroid
                dz = abs(z_at(mean, c.x, c.y) - z_at(eqs[k], c.x, c.y))
                res.moves[planes[k].id]["one_face_with"] = planes[j if k == i else i].id
                res.moves[planes[k].id]["one_face_dz_ft"] = round(dz, 2)
            eqs[i] = eqs[j] = mean  # type: ignore[assignment]


def _surface(area: float, pitch: float) -> float:
    return area / math.cos(math.atan(pitch / 12.0))


def _ring(r: Any) -> list[list[float]]:
    return [[round(float(x), 2) + 0.0, round(float(y), 2) + 0.0] for x, y in list(r.coords)[:-1]]


def _rebuilt(pl: Any, g: Polygon, eq: Eq, method: str, section: int, raw: BaseGeometry | None = None) -> Any:
    g = orient(g, 1.0)
    area = float(g.area)
    asp = aspect_of(eq)
    kw: dict[str, Any] = {"polygon": _ring(g.exterior), "holes": [_ring(h) for h in g.interiors],
                          "plan_area_sqft": round(area, 1), "surface_area_sqft": round(_surface(area, float(pl.pitch_rise)), 1),
                          "straightened": True, "plane_eq": [round(eq[0], 5), round(eq[1], 5), round(eq[2], 3)],
                          "aspect_deg": pl.aspect_deg if asp is None or pl.aspect_deg is None else asp,
                          "raw_plan_area_sqft": pl.raw_plan_area_sqft if pl.raw_plan_area_sqft is not None else pl.plan_area_sqft}
    if raw is not None and area > 0:  # the share of the NEW polygon that LiDAR did not see (gap filling's share)
        seen = raw.intersection(g).area if not raw.is_empty else 0.0
        kw["filled_pct"] = round(100.0 * max(0.0, area - seen) / area, 1)
    names = {f.name for f in dataclasses.fields(pl)}
    extra = {"straighten_method": method, "section": section}
    out = dataclasses.replace(pl, **kw, **{k: v for k, v in extra.items() if k in names})
    for k, v in extra.items():
        if k not in names:
            object.__setattr__(out, k, v)
    return out


def envelope_detail(planes: list[Any], raw: dict[str, BaseGeometry] | None, region: BaseGeometry) -> EnvelopeResult:
    """The envelope partition with everything it found (see the module docstring). Never raises.

    The planes' ``plane_eq`` must share one height datum (``planes._snap`` builds them from the blocks' absolute
    ``mean_z_ft`` minus the median local ground): heights above each block's LOCAL ground differ by feet on a sloping
    lot and would put every ridge and valley in the wrong place.
    """
    try:
        res = _run(planes, raw, region)
        if res.gate_failure is not None and res.planes:
            if any(len(s["planes"]) > SPLIT_MIN_PLANES for s in res.sections):
                part = _run(planes, raw, region, split=True)  # a big section: partitioned part by part
                if part.gate_failure is None:
                    part.steps = "split"
                    part.refused = res.gate_failure
                    return part
            # the square step lines did not pass: the older reading (steps along the border, diagonal when it is)
            old = _run(planes, raw, region, legacy=True)
            if old.gate_failure is None:
                old.steps = "legacy"
                old.refused = res.gate_failure
                return old
        return res
    except Exception:  # any internal error: the caller keeps its own planes (this step may only make a roof better)
        log.warning("envelope partition failed", exc_info=True)
        return EnvelopeResult(gate_failure="an error")


def envelope_planes(planes: list[Any], raw: dict[str, BaseGeometry] | None,
                    region: BaseGeometry) -> tuple[list[Any], list[dict[str, Any]]] | None:
    """``(planes, borders)`` partitioned by plane equations, or None when the gate fails (keep the input)."""
    res = envelope_detail(planes, raw, region)
    if res.gate_failure is not None:
        log.info("envelope partition not used: %s", res.gate_failure)
        return None
    return res.planes, res.borders


def _raws(planes: list[Any], raw: dict[str, BaseGeometry] | None, fp: Polygon) -> list[BaseGeometry]:
    """Each plane's raw cluster inside the outline: from ``raw`` (by id) when given, else from the planes' own
    ``raw_polygon`` rings with overlaps going to the larger cluster (as ``planes_gaps._resolve_overlaps`` does)."""
    if raw is not None:
        out = [raw[p.id].intersection(fp) if p.id in raw and raw[p.id] is not None else Polygon() for p in planes]
        return [r if r.is_valid else r.buffer(0) for r in out]
    own = []
    for p in planes:
        ring = getattr(p, "raw_polygon", None)
        g = Polygon(ring) if ring and len(ring) >= 3 else Polygon()
        own.append((g if g.is_valid else g.buffer(0)).intersection(fp))
    taken: BaseGeometry = Polygon()
    out = [Polygon()] * len(planes)
    for k in sorted(range(len(planes)), key=lambda k: (-own[k].area, k)):
        piece = own[k].difference(taken)
        taken = taken.union(own[k])
        parts = polygons_of(piece)
        out[k] = max(parts, key=lambda q: q.area) if parts else Polygon()
    return out


def _run(planes: list[Any], raw: dict[str, BaseGeometry] | None, region: BaseGeometry,
         legacy: bool = False, split: bool = False) -> EnvelopeResult:
    parts = polygons_of(region)
    if len(planes) < 1 or not parts:
        return EnvelopeResult(gate_failure="no planes or no outline")
    fp = max(parts, key=lambda p: p.area)
    n = len(planes)
    shapes = [p.shape() if p.shape().is_valid else p.shape().buffer(0) for p in planes]
    outside = [p.id for p, g in zip(planes, shapes, strict=True)
               if g.area >= LOSE_OK_SQFT and g.difference(fp).area > 0.5 * g.area]
    if outside:  # a plane on another part of a multi-part region (a detached carport) would vanish unseen
        return EnvelopeResult(gate_failure=f"plane {outside[0]} lies outside the main part of the region")
    raws = _raws(planes, raw, fp)
    u = axis_deg(fp)
    dirs = [(u + 45.0 * k) % 180.0 for k in range(4)]
    res = EnvelopeResult()
    eqs: list[Eq] = []
    if not all(math.isfinite(v) for p in planes for v in eq_of(p)):
        return EnvelopeResult(gate_failure="a plane equation is not finite")
    for p, r, s in zip(planes, raws, shapes, strict=True):
        eq, turn, dz = square_eq(eq_of(p), r if not r.is_empty else s, u)
        eqs.append(eq)
        res.moves[p.id] = {"turn_deg": round(turn, 2), "max_dz_ft": round(dz, 2)}
    _one_face(planes, raws, shapes, eqs, res)
    shared = neighbours(shapes)
    sec = sections(shared, eqs, raws, shapes, dirs)
    regions = section_regions(fp, shapes, raws, sec, u, eqs, legacy)
    owner: list[list[BaseGeometry]] = [[] for _ in range(n)]
    for q, reg in enumerate(regions):
        members = [k for k in range(n) if sec[k] == q]
        if reg.is_empty or not members:
            continue
        parts = [(reg, members)]
        if split and len(members) > SPLIT_MIN_PLANES:
            groups = subsections(members, shared, eqs, raws, shapes)
            if len(groups) > 1:
                parts = list(zip(sub_regions(reg, groups, shared, eqs, raws, shapes, dirs), groups, strict=True))
        for sub, (part, ks) in enumerate(parts):
            if part.is_empty:
                continue
            cells, labels, rec = partition(part, ks, raws, shapes, eqs, shared, dirs, u, fp, res.lines, len(parts) > 1)
            res.sections.append({"section": q, "planes": [planes[k].id for k in ks], **rec,
                                 "starved": [planes[k].id for k in rec["starved"]],
                                 "boxed": [planes[k].id for k in rec["boxed"]], **({"part": sub} if len(parts) > 1 else {})})
            for c, lab in zip(cells, labels, strict=True):
                owner[lab].append(c)
    merged = [unary_union(cs) if cs else Polygon() for cs in owner]
    merged = rehome_detached(merged, raws)
    final = _finish_polys(thin_strips(merged, raws, fp), fp.exterior, SPLIT_WELD_FT if split else WELD_FT)
    method_of = {pid: s["method"] for s in res.sections for pid in s["planes"]}
    out, out_eqs, out_shapes, out_sec, out_raws = [], [], [], [], []
    for k, (p, g) in enumerate(zip(planes, final, strict=True)):
        if g.is_empty:
            res.merged_small.append(p.id)
            continue
        out.append(_rebuilt(p, g, eqs[k], method_of.get(p.id, "envelope"), sec[k], raws[k]))
        out_eqs.append(eqs[k])
        out_shapes.append(g)
        out_sec.append(sec[k])
        out_raws.append(raws[k] if not raws[k].is_empty else g)
    res.planes = out
    res.borders = borders([p.id for p in out], out_shapes, out_eqs, out_sec, out_raws)
    res.gate_failure = gate(planes, out, raws, fp, res.merged_small)
    return res
