"""The late stages of a run: facets and edges, totals, quality verdict, back to the world frame."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

from . import axes
from .cleanup import valid_polygon
from .edges import build_edges
from .errors import EngineError
from .facets import facet_stats, supported_pct
from .params import EngineParams
from .partition import PartitionRun, explode
from .plane_math import aspect_deg, pitch_rise, pres
from .ring import ring_filter
from .signals import quality, ring_roof_extra_ratio, tree_contact_pct
from .state import Run
from .totals import footprint_totals, roof_totals
from .types import Edge, EngineResult, Facet, Outline, Partition, Plane, Quality


def _plane_objs(planes: list, qlab: np.ndarray, q: np.ndarray) -> list[Plane]:
    out = []
    for i, pl in enumerate(planes):
        m = qlab == i
        rms = float(pres(pl, q[m]).std()) if m.sum() > 1 else 0.0
        out.append(Plane(float(pl[0]), float(pl[1]), float(pl[2]), int(m.sum()), rms))
    return out


def _borderline(facets: list[Facet], p: EngineParams) -> list[str]:
    total = sum(f.area_sqft for f in facets) or 1.0
    ids = [f.id for f in facets if f.pitch_fit is not None and f.pitch_sigma is not None
           and abs(f.pitch_fit - p.flat_cut_rise) <= p.borderline_sigma * f.pitch_sigma
           and f.area_sqft > p.borderline_area_share * total]
    for f in facets:
        f.borderline = f.id in ids
    return ids


def _supported(facets: list[Facet], q: np.ndarray, p: EngineParams) -> float | None:
    tree = cKDTree(q[:, :2])
    for f in facets:
        sp = supported_pct(f.polygon, tree, p)
        f.supported_pct = None if sp is None else round(sp, 1)
    wa = [(f.area_sqft, f.supported_pct) for f in facets if f.supported_pct is not None]
    return round(sum(a * b for a, b in wa) / max(sum(a for a, _ in wa), 1e-9), 1) if wa else None


def _to_world(ang: float, facets: list[Facet], edges: list[Edge], outline: Polygon) -> Polygon:
    """Rotate drawn facets, edges and outline back to the world frame (in place for facets and edges)."""
    if not ang:
        return outline
    for f in facets:
        f.polygon = valid_polygon(axes.poly_to_world(f.polygon, ang))
        pl = axes.rotate_plane(f.plane, ang)
        f.plane = (float(pl[0]), float(pl[1]), float(pl[2]))
        if math.hypot(f.plane[0], f.plane[1]) > 1e-3:
            f.aspect_deg = float(aspect_deg(f.plane))
    for e in edges:
        e.p0 = tuple(axes.point_to_world(e.p0, ang))
        e.p1 = tuple(axes.point_to_world(e.p1, ang))
    return axes.poly_to_world(outline, ang)


def quality_stage(run: Run, facets: list[Facet], o: Polygon, crop: np.ndarray, plab: np.ndarray) -> Quality:
    """Signals and verdict; a failure here is reported as verdict ``unknown`` and never aborts the measurement."""
    p = run.ctx.p
    try:
        out = _quality(run, facets, o, crop, plab, p)
    except EngineError:
        raise
    except Exception as ex:  # noqa: BLE001 - the measurement stands; the verdict says the signals failed
        return Quality(verdict="unknown", error=str(ex)[:80])
    if run.diag.get("no_planes_found") or run.diag.get("assigned_pct", 100.0) < p.planes_min_assigned_pct:
        out.reasons.append("planes_not_found")  # a roof drawn from (almost) no planes is never a confident drawing
        if out.verdict in ("ok", "not_exact_parcel", "low_density"):
            out.verdict = "poor_fit"
    return out


def _quality(run: Run, facets: list[Facet], o: Polygon, crop: np.ndarray, plab: np.ndarray, p: EngineParams) -> Quality:
    tree_pct = tree_contact_pct(o, crop[plab < 0])
    extra = ring_roof_extra_ratio(run.context, run.wall_world, p)
    pall = run.pts_all[shapely.contains_xy(run.wall.buffer(p.crop_buffer_m), run.pts_all[:, 0], run.pts_all[:, 1])]
    pall = ring_filter(pall, run.wall, p, {})  # the same points the planes were fitted on
    return quality(facets, pall, o, run.wall, run.parcel_match, run.source, run.diag.get("supported_pct"),
                   run.diag.get("support_area_m2", 0), extra, tree_pct, p)


def facets_stage(run: Run, best: PartitionRun, q: np.ndarray, o: Polygon) -> tuple[list[Facet], list[Edge], dict[str, Any]]:
    """Facets, edges, borderline flags, supported share and the totals of the one (drawn) roof."""
    p, diag, ctx = run.ctx.p, run.diag, run.ctx
    facets = facet_stats(explode(best.items), best.planes, q, p)
    diag["facets_per_20m2"] = round(len(facets) / (o.area / 20.0), 2)
    jq = run.jump_pts if run.jump_pts is not None else q
    edges = build_edges(facets, jq, ctx)
    ids = _borderline(facets, p)
    diag["borderline"] = bool(ids)
    diag["borderline_facets"] = ids
    diag["supported_pct"] = _supported(facets, q, p)
    tot = roof_totals(facets, edges, set(ids), p)
    tot.update(footprint_totals(facets, o, run.wall, diag.get("overhang_applied_m", [])))
    run.stages.facets, run.stages.edges = [replace(f) for f in facets], [replace(e) for e in edges]
    return facets, edges, tot


def assemble(run: Run, facets: list[Facet], edges: list[Edge], tot: dict, o: Polygon,
              best: PartitionRun, q: np.ndarray, qlab: np.ndarray, quality_: Quality) -> EngineResult:
    p, diag, ang = run.ctx.p, run.diag, run.ang
    diag["quality"] = quality_.to_dict()
    o_world = _to_world(ang, facets, edges, o)
    world_planes = [axes.rotate_plane(pl, ang) if ang else pl for pl in best.planes]
    diag["support_planes"] = [[round(pitch_rise(pl), 2), round(aspect_deg(pl), 1)] for pl in world_planes]
    h = best.origin[2]
    partition = Partition(best.labels, best.origin[0], best.origin[1], h, _plane_objs(best.planes, qlab, q), best.beta)
    outline = Outline(o_world, run.source, run.county,
                      tuple(diag.get("overhang_measured_m", [])), tuple(diag.get("overhang_applied_m", [])),
                      float(diag.get("support_area_m2", 0.0)))
    return EngineResult(facets=facets, edges=edges, outline=outline, totals=tot, quality=quality_,
                        planes=[Plane(float(pl[0]), float(pl[1]), float(pl[2])) for pl in world_planes],
                        partition=partition, diagnostics=diag, timings=run.timings, params_hash=p.stable_hash())


