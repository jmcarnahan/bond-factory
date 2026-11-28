"""The engine pipeline: roof points + footprint in, facets / edges / totals / quality out.

Stages: building frame -> plane detection -> roof-edge outline -> global labelling (partition) -> facets and edges ->
cost-sheet totals -> quality verdict -> back to the world frame. Metres in, feet in the totals.
"""

from __future__ import annotations

import math
import time
from typing import Any

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from . import axes
from .detect import detect_planes
from .edge_measure import jump_points
from .errors import Ctx, EngineInputError
from .facets import SQM2SQFT as SQM
from .finish import assemble, facets_stage, quality_stage
from .outline import build_outline, overhang_per_side
from .params import EngineParams
from .partition import build_partition
from .ring import ring_filter
from .state import Run, Stages
from .types import EngineResult, Quality, RoofPoints


def is_county_outline(source: str) -> bool:
    """County outlines are wall lines (the roof edge lies up to 1.5 m out); OSM / Overture / hull outlines are already
    near the roof edge (a tighter outward clamp)."""
    s = (source or "").lower()
    return "county" in s or "lacounty" in s or "lariac" in s


def refused(reason: str, params: EngineParams, density: float | None = None, outline_source: str = "") -> EngineResult:
    """A result with no facets; ``quality.verdict`` carries the reason."""
    q = Quality(verdict=reason, reasons=[reason], density=density, outline_source=outline_source, brief=True)
    return EngineResult(facets=[], edges=[], outline=None, totals={}, quality=q, params_hash=params.stable_hash())


def clean_footprint(footprint: BaseGeometry) -> Polygon:
    """The footprint as one valid Polygon (the largest part of a multipolygon); EngineInputError when unusable."""
    if footprint is None or footprint.is_empty:
        raise EngineInputError("bad_footprint")
    footprint = shapely.force_2d(footprint)
    if not np.isfinite(np.asarray(footprint.bounds, float)).all():
        raise EngineInputError("bad_footprint")
    if not footprint.is_valid:
        footprint = shapely.make_valid(footprint)
    polys = [g for g in (footprint.geoms if hasattr(footprint, "geoms") else [footprint]) if g.geom_type == "Polygon"]
    if not polys:
        raise EngineInputError("bad_footprint")
    poly = max(polys, key=lambda g: g.area)
    if poly.area < 4.0:
        raise EngineInputError("bad_footprint")
    return poly


def _finite_xyz(points: RoofPoints) -> np.ndarray:
    """The roof returns as an (n, 3) float array with non-finite rows dropped."""
    try:
        xyz = np.asarray(points.xyz, float)
    except (TypeError, ValueError) as ex:
        raise EngineInputError("bad_points") from ex
    if xyz.size == 0:
        return np.zeros((0, 3))
    if xyz.ndim != 2 or xyz.shape[1] < 3:
        raise EngineInputError("bad_points")
    xyz = xyz[:, :3]
    return xyz[np.isfinite(xyz).all(1)]


def _crop(pts: np.ndarray, wall: Polygon, p: EngineParams, diag: dict[str, Any]) -> np.ndarray:
    """Points within footprint + 1.3 m; a dense cloud is thinned to one point per 0.22 m voxel (then capped)."""
    crop = pts[shapely.contains_xy(wall.buffer(p.crop_buffer_m), pts[:, 0], pts[:, 1])]
    if len(crop) > p.thin_above_pts:
        key = np.floor(crop[:, :3] / np.array([p.thin_voxel_m] * 3)).astype(np.int64)
        _, ui = np.unique(key, axis=0, return_index=True)
        crop = crop[np.sort(ui)]
        diag["thinned"] = True
    if len(crop) > p.max_points:
        crop = crop[np.linspace(0, len(crop) - 1, p.max_points).astype(int)]
        diag["capped"] = True
    return crop


def _unusable(crop: np.ndarray, p: EngineParams) -> bool:
    """Too few points, or all on one line: nothing to fit a plane to."""
    if len(crop) < p.min_points:
        return True
    xy = crop[:, :2] - crop[:, :2].mean(0)
    return bool(np.linalg.svd(xy, compute_uv=False)[-1] < 1e-3 * math.sqrt(len(crop)))


def _detect_stage(run: Run, thetas: list[float]) -> tuple[list, np.ndarray, np.ndarray] | None:
    """Crop and detect planes. Returns (planes, crop, labels), or None when the crop is unusable."""
    p = run.ctx.p
    run.stages.crop = crop = ring_filter(_crop(run.pts_all, run.wall, p, run.diag), run.wall, p, run.diag)
    if _unusable(crop, p):
        return None
    planes, plab = detect_planes(crop, run.wall, thetas if len(thetas) > 1 else thetas[0], run.ctx)
    run.diag["n_points"] = len(crop)
    run.diag["n_planes"] = len(planes)
    run.diag["axis_deg"] = round(thetas[0], 1)
    run.diag["assigned_pct"] = round(100 * float((plab >= 0).mean()), 1)
    if len(planes) == 0:  # no plane found: one horizontal plane through the points (flagged in diagnostics)
        planes = [np.array([0.0, 0.0, float(np.median(crop[:, 2]))])]
        plab = np.zeros(len(crop), int)
        run.diag["no_planes_found"] = True
    run.stages.planes, run.stages.plab = planes, plab
    return planes, crop, plab


def _outline_stage(run: Run, q: np.ndarray, qlab: np.ndarray, theta: float) -> Polygon:
    p = run.ctx.p
    run.diag["outline_provider"] = run.source
    wide = None
    if run.context is not None:
        wide = np.asarray(run.context, float)[:, :4].copy()
        if p.s3_axis:
            wide[:, :2] = axes.to_building_frame(wide[:, :2], run.ang)
    o, od = build_outline(q, qlab, run.stages.planes, run.wall, theta, run.county, wide,
                          run.pts_all, p)
    run.diag.update(od)
    if o.geom_type != "Polygon":
        o = max(o.geoms, key=lambda g: g.area)
    return Polygon(o.exterior)


def _outline_sensitivity(run: Run, o: Polygon) -> None:
    d = run.diag
    d["overhang_m_per_side"] = overhang_per_side(run.wall, o)
    d["outline_area_sqft_footprint"] = round(run.wall.area * SQM, 0)
    d["outline_area_sqft_points"] = round(o.area * SQM, 0)
    d["outline_sens_sqft_minus015"] = round(o.buffer(-0.15, join_style=2).area * SQM, 0)
    d["outline_sens_sqft_plus015"] = round(o.buffer(0.15, join_style=2).area * SQM, 0)


def measure_stages(points: RoofPoints, footprint_m: BaseGeometry, *, params: EngineParams, deadline: float | None,
                   outline_source: str, parcel_match: str | None, context: np.ndarray | None
                   ) -> tuple[EngineResult, Stages]:
    """Run the whole engine; also return the intermediate products (building frame) for tests."""
    ctx = Ctx(params, deadline)
    p = params
    if context is not None and not (isinstance(context, np.ndarray) and context.ndim == 2 and context.shape[1] >= 4):
        context = None  # a wide cloud must be (m, 4): x, y, z, class; anything else is ignored
    stages = Stages()
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    ctx.check()
    try:
        wall_world = clean_footprint(footprint_m)
        xyz = _finite_xyz(points)
    except EngineInputError as ex:
        return refused(str(ex), p, outline_source=outline_source), stages
    diag: dict[str, Any] = {}
    ang = axes.dominant_axis(wall_world) if p.s3_axis else 0.0
    wall = affinity.rotate(wall_world, -ang, origin=(0, 0)) if p.s3_axis else wall_world
    pts_all = xyz.copy()
    if p.s3_axis:
        pts_all[:, :2] = axes.to_building_frame(xyz[:, :2], ang)
        diag["frame_rot_deg"] = round(ang, 2)
    theta = 0.0 if p.s3_axis else axes.dominant_axis(wall_world)
    thetas = [theta]  # one building axis (a second axis changed nothing in the spike's medians and was removed)
    diag["axes_deg"] = [round(theta, 1)]
    stages.theta, stages.frame_deg = theta, ang
    run = Run(ctx, wall, wall_world, pts_all, stages, diag, is_county_outline(outline_source), outline_source,
               parcel_match, context, ang, timings, ground_z=float(points.ground_z))
    jp = jump_points(context, wall_world)
    if jp is not None and p.s3_axis and len(jp):
        jp = jp.copy()
        jp[:, :2] = axes.to_building_frame(jp[:, :2], ang)
    run.jump_pts = jp
    t = run.tick("frame", t0)
    detected = _detect_stage(run, thetas)
    if detected is None:
        return refused("lidar_too_sparse", p, outline_source=outline_source), stages
    planes, crop, plab = detected
    t = run.tick("planes", t)
    ok = plab >= 0
    q, qlab = crop[ok], plab[ok]
    o = _outline_stage(run, q, qlab, theta)
    stages.outline = o
    dens0 = float(shapely.contains_xy(o, pts_all[:, 0], pts_all[:, 1]).sum() / max(o.area, 1.0))
    if dens0 < p.density_refuse and p.refuse_sparse:
        return refused("lidar_too_sparse", p, round(dens0, 1), outline_source), stages
    _outline_sensitivity(run, o)
    t = run.tick("outline", t)
    best, h = build_partition(o, q, qlab, planes, theta, ctx, crop)
    stages.run = best
    diag["grid_m"] = round(h, 3)
    diag.update(best.diag)
    diag["beta_used"] = best.beta
    t = run.tick("partition", t)
    facets, edges = facets_stage(run, best, q, o)
    t = run.tick("facets", t)
    quality_ = quality_stage(run, facets, o, crop, plab)
    flat_sq = round(sum(f.area_sqft for f in facets if f.roof_type == "flat"), 1)
    pitched_sq = round(sum(f.area_sqft for f in facets if f.roof_type != "flat"), 1)
    if flat_sq + pitched_sq > 0:  # the pitched / flat split of the drawn roof
        quality_.flat_share = flat_sq / (flat_sq + pitched_sq)  # UNROUNDED: round(0.8996, 3) would cross a 0.90 line
    res = assemble(run, facets, edges, o, best, q, best.qlab, quality_)
    run.tick("finish", t)
    return res, stages
