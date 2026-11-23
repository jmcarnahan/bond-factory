"""Plane detection: normals, region growing, merging coplanar planes and dropping what is not a roof facet.

Input is the roof point cloud in a local metric frame (the building frame when axis alignment is on); output is the
list of planes ``(a, b, c)`` and a label per point (-1 = not on a plane). Metres throughout.
"""

from __future__ import annotations

import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from shapely.geometry.base import BaseGeometry

from .errors import Ctx
from .grow import assign, drop_islands, refit, region_grow
from .normals import knn_normals
from .params import EngineParams
from .plane_math import compact, fit_plane, pdist, pitch_rise
from .regularise import merge_identical, regularise

_DEAD_PLANE = np.array([0.0, 0.0, 1e9])


def _nearby(pa: np.ndarray, pb: np.ndarray, r: float) -> bool:
    """True when some point of ``pb`` is within ``r`` (plan view) of ``pa``."""
    d, _ = cKDTree(pa[:, :2]).query(pb[:, :2], k=1)
    return bool(d.min() < r)


def merge_coplanar(pts: np.ndarray, lab: np.ndarray, planes: list, p: EngineParams,
                   ctx: Ctx) -> tuple[np.ndarray, list]:
    """Merge planes with almost the same gradient and mutual distance whose points touch; refit the union."""
    changed = True
    while changed:
        ctx.check()
        changed = False
        for i in range(len(planes)):
            for j in range(i + 1, len(planes)):
                mi, mj = lab == i, lab == j
                if mi.sum() < 4 or mj.sum() < 4:
                    continue
                if np.linalg.norm(planes[i][:2] - planes[j][:2]) > p.coplanar_gdiff:
                    continue
                dd = np.concatenate([pdist(planes[i], pts[mj]), pdist(planes[j], pts[mi])]).mean()
                if dd > p.coplanar_mdist_m or not _nearby(pts[mi], pts[mj], p.coplanar_near_m):
                    continue
                pl = fit_plane(pts[mi | mj])
                if pdist(pl, pts[mi | mj]).std() > p.coplanar_rms_m:
                    continue
                planes[i] = pl
                lab[mj] = i
                planes[j] = _DEAD_PLANE.copy()
                changed = True
    return compact(lab, planes)


def support_area(pm: np.ndarray, p: EngineParams) -> float:
    """Area (m2) of the 0.35 m cells that hold at least one point."""
    cells = len(set(map(tuple, np.floor(pm[:, :2] / p.support_cell_m).astype(int))))
    return cells * p.support_cell_m ** 2


def support_radius(pm: np.ndarray, p: EngineParams) -> float:
    """Largest inscribed radius (m) of the closed 0.3 m support raster of the points."""
    step = p.support_grid_m
    ij = np.floor((pm[:, :2] - pm[:, :2].min(0)) / step).astype(int)
    grid = np.zeros(tuple(ij.max(0) + 5), bool)
    grid[ij[:, 0] + 2, ij[:, 1] + 2] = True
    grid = ndi.binary_closing(grid, iterations=2)
    return float(ndi.distance_transform_edt(grid).max() * step)


def _is_good_small(rms: float, n: int, area: float, plane, p: EngineParams) -> bool:
    return (rms < p.good_small_rms_m and n >= p.plane_min_pts and area >= p.good_small_area_m2
            and pitch_rise(plane) >= p.good_small_pitch)


def _filter_first(pts: np.ndarray, lab: np.ndarray, planes: list, p: EngineParams) -> tuple[np.ndarray, list]:
    """Drop planes with too few points, too little area, too much noise, too steep or strip-shaped."""
    keep = []
    for i, pl in enumerate(planes):
        m = lab == i
        n = int(m.sum())
        if n < p.plane_min_pts:
            continue
        area = support_area(pts[m], p)
        rms = pdist(pl, pts[m]).std()
        good_small = _is_good_small(rms, n, area, pl, p)
        if area < p.plane_min_area_m2 and not good_small:
            continue
        if rms > p.plane_rms_max_m:
            continue
        steep = pitch_rise(pl)
        if steep > p.plane_pitch_max and not (steep <= p.plane_pitch_hard and area >= p.plane_steep_area_m2):
            continue  # steeper than a roof: wall, tree or noise, unless it is a big clean plane (a real 14-18/12 roof)
        if support_radius(pts[m], p) < p.thin_radius_m and area < p.thin_area_m2 and not good_small:
            continue
        keep.append(i)
    remap = {o: n for n, o in enumerate(keep)}
    lab2 = np.array([remap.get(v, -1) if v >= 0 else -1 for v in lab], dtype=int)
    return lab2, [planes[i] for i in keep]


def _filter_second(pts: np.ndarray, lab: np.ndarray, planes: list, footprint: BaseGeometry | None,
                   p: EngineParams, ctx: Ctx) -> tuple[np.ndarray, list]:
    """Second pass: strips and planes mostly outside the footprint are not facets."""
    changed = True
    buf = footprint.buffer(p.outside_buffer_m) if footprint is not None else None
    while changed:
        ctx.check()
        changed = False
        for i in range(len(planes)):
            m = lab == i
            if m.sum() == 0:
                continue
            area = support_area(pts[m], p)
            rad = support_radius(pts[m], p)
            inside = shapely.contains_xy(buf, pts[m, 0], pts[m, 1]).mean() if buf is not None else 1.0
            rms = pdist(planes[i], pts[m]).std()
            gs = _is_good_small(rms, int(m.sum()), area, planes[i], p)
            thin = rad < p.thin2_radius_m and area < p.thin2_area_m2 and not (gs and rad >= p.thin2_keep_radius_m)
            small = area < p.plane_min_area_m2 and not gs
            if thin or small or inside < p.outside_min_share:
                lab[m] = -1
                planes[i] = _DEAD_PLANE.copy()
                changed = True
    return compact(lab, planes)


def _reset_offsets(pts: np.ndarray, lab: np.ndarray, planes: list) -> None:
    """Set each plane's offset to the median residual of its points (gradient unchanged)."""
    for i, pl in enumerate(planes):
        r = pts[lab == i, 2] - pl[0] * pts[lab == i, 0] - pl[1] * pts[lab == i, 1]
        pl[2] = np.median(r)


def detect_planes(pts: np.ndarray, footprint: BaseGeometry | None, theta: float | list[float],
                  ctx: Ctx) -> tuple[list, np.ndarray]:
    """Detect, merge, filter and regularise the roof planes of ``pts`` (n, 3). Returns (planes, label per point)."""
    p = ctx.p
    normals, curv, tree = knn_normals(pts, p)
    lab, planes = region_grow(pts, normals, curv, tree, ctx)
    lab = assign(pts, planes, p.assign_tol_m)
    lab, planes = refit(pts, lab, planes, p, iters=3)
    lab, planes = merge_coplanar(pts, lab, planes, p, ctx)
    lab, planes = refit(pts, lab, planes, p, iters=2)
    lab, planes = _filter_first(pts, lab, planes, p)
    lab, planes = refit(pts, lab, planes, p, iters=2)
    planes = regularise(pts, lab, planes, theta, p)
    lab = assign(pts, planes, p.assign_tol_m)
    lab, planes = merge_identical(pts, lab, planes, p, ctx)
    _reset_offsets(pts, lab, planes)
    lab = assign(pts, planes, p.assign_tol_m)
    if p.assign_drop_islands:
        lab = drop_islands(pts, lab, planes, p)
    lab, planes = _filter_second(pts, lab, planes, footprint, p, ctx)
    lab, planes = refit(pts, lab, planes, p, iters=1)
    return planes, lab
