"""Cost-sheet totals and quality signals with the verdict (plan 3.1 key names, plan 3.9 thresholds).

Everything here works in whatever metric frame the facets are in; areas are square feet, lengths feet.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .edges import M2F
from .facets import SQM2SQFT
from .normals import knn_normals
from .params import EngineParams
from .types import Edge, Facet, Quality

_NOT_ROOF_CLASSES = [3, 4, 5, 7, 9]  # ASPRS vegetation, noise, water classes: never roof


def cost_outputs(facets: list[Facet], edges: list[Edge], outline: Polygon, wall: Polygon,
                 borderline_ids: set[str], overhang_applied_m: list[float], p: EngineParams) -> dict[str, Any]:
    """The extra totals the cost sheet reads, from the (priced) facets and edges and the wall-line footprint."""
    t: dict[str, Any] = {}
    surf = sum(f.area_sqft for f in facets)
    pitched = [f for f in facets if f.roof_type == "pitched"]
    flat = [f for f in facets if f.roof_type == "flat"]
    ap, af = sum(f.area_sqft for f in pitched), sum(f.area_sqft for f in flat)
    t["planes_surface_area_sqft"] = round(surf, 1)  # roof-edge surface (priced default)
    t["planes_pitch_weighted"] = round(sum(f.area_sqft * f.pitch_rise for f in pitched) / ap, 2) if ap > 0 else 0.0
    ext = [e for e in edges if len(e.facets) == 1]
    t["outline_perimeter_ft"] = round(sum(e.length_ft for e in ext if e.type in ("eave", "rake", "flat_edge")), 1)
    flat_ids = {f.id for f in flat}  # a crease between two low-slope (under 2/12) facets takes no ridge cap
    t["ridge_cap_ridge_hip_ft"] = round(sum(e.length_ft for e in edges if e.type in ("ridge", "hip")
                                            and not (len(e.facets) == 2 and set(e.facets) <= flat_ids)), 1)
    t["high_edge_ft"] = round(sum(e.length_ft for e in ext if e.high_edge), 1)  # level high sides (rake metal, no cap)
    t["roofing_pitched_sqft"] = round(ap, 1)
    t["roofing_flat_sqft"] = round(af, 1)
    t["roofing_pitched_squares"] = round(ap / 100, 2)
    t["roofing_flat_squares"] = round(af / 100, 2)
    t["low_slope_confirm_sqft"] = round(sum(f.area_sqft for f in facets if f.id in borderline_ids), 1)
    wl_area = 0.0
    clipped = []
    for f in facets:  # the same facets cut to the wall line (what the plan calls area_sqft_wall_line)
        c = f.polygon.intersection(wall)
        clipped.append(c)
        wl_area += c.area * SQM2SQFT * math.sqrt(1 + (f.pitch_rise / 12.0) ** 2)
    t["area_sqft_wall_line"] = round(wl_area, 1)
    u = unary_union(clipped) if clipped else None
    t["outline_perimeter_wall_ft"] = round(u.length * M2F, 1) if u is not None and not u.is_empty else None
    oh = [v for v in overhang_applied_m if v is not None]
    t["overhang_ft_median"] = round(float(np.median(oh)) * M2F, 2) if oh else None
    t["flat_edge_ft"] = round(sum(e.length_ft for e in edges if e.type == "flat_edge"), 1)
    t["level_change_ft"] = round(sum(e.length_ft for e in edges if e.type == "level_change"), 1)
    t["roof_edge_perimeter_geom_ft"] = round(outline.length * M2F, 1)
    hv = sum(e.length_ft for e in edges if e.type in ("hip", "valley"))
    sq = surf / 100.0
    hvq = hv / sq if sq > 0 else 0.0
    cut = len(facets) >= p.cut_up_facets or hvq >= p.cut_up_hv_per_sq
    t["complexity"] = {"facets": len(facets), "hip_valley_ft_per_square": round(hvq, 2),
                       "hint": "cut_up" if cut else "simple"}
    return t


def _fit_shares(facets: list[Facet], pts: np.ndarray, p: EngineParams) -> tuple[float | None, float | None, float | None,
                                                                             float | None, float | None]:
    """(fit_all, fit_covered, coverage, fit_clear, tree_cover_pct) over the roof returns ``pts``.

    fit_all: share within ``fit_tol_m`` of the plane of the facet they fall in (a return outside every facet counts as
    a miss). fit_covered: the same over the returns inside a facet. Canopy: a return more than ``canopy_above_m`` ABOVE
    the surface under it (inside a facet, or outside one but within 2 m of it: the surface there is that facet's
    plane): trees over the eaves, not roof. fit_clear is fit_all with the canopy left out of the count (reported, not part of the verdict); tree_cover_pct
    the canopy's share of all returns. Returns far BELOW the surface or off it stay misses."""
    n = len(pts)
    assigned = np.full(n, -1)
    for i, f in enumerate(facets):
        c = shapely.contains_xy(f.polygon, pts[:, 0], pts[:, 1])
        assigned[(assigned < 0) & c] = i
    ins = assigned >= 0
    ok = np.zeros(n, bool)
    canopy = np.zeros(n, bool)
    for i, f in enumerate(facets):
        m = assigned == i
        if m.any():
            pl = f.plane
            r = pts[m, 2] - (pl[0] * pts[m, 0] + pl[1] * pts[m, 1] + pl[2])
            ok[m] = np.abs(r) <= p.fit_tol_m
            canopy[np.nonzero(m)[0][r > p.canopy_above_m]] = True
    out = np.nonzero(~ins)[0]
    if len(out) and facets:  # outside every facet: judged against the nearest facet's plane when one is within 2 m
        pp = shapely.points(pts[out, 0], pts[out, 1])
        d = np.stack([shapely.distance(f.polygon, pp) for f in facets])
        near = d.argmin(0)
        close = d.min(0) <= 2.0
        for i, f in enumerate(facets):
            m = close & (near == i)
            if m.any():
                pl = f.plane
                r = pts[out[m], 2] - (pl[0] * pts[out[m], 0] + pl[1] * pts[out[m], 1] + pl[2])
                canopy[out[m][r > p.canopy_above_m]] = True
    fit_all = round(float(ok.sum() / n), 3) if n else None
    fit_cov = round(float(ok.sum() / ins.sum()), 3) if ins.sum() else None
    clear_n = n - int(canopy.sum())
    fit_clear = round(float(ok.sum() / clear_n), 3) if clear_n > 0 else None
    tree = round(100.0 * float(canopy.mean()), 1) if n else None
    return fit_all, fit_cov, round(float(ins.mean()), 3) if n else None, fit_clear, tree


def quality(facets: list[Facet], pts: np.ndarray, outline: Polygon, wall: Polygon, parcel_match: str | None,
            provider: str, supported_pct: float | None, support_area_m2: float, overhang_scale: float,
            extra: float | None, tree_pct: float | None, p: EngineParams) -> Quality:
    """Plan 3.9 signals and verdict. ``pts`` are all roof points in the frame of the facets."""
    fit_all, fit_cov, cover_pts, fit_clear, tree_cover = _fit_shares(facets, pts, p)
    n = len(pts)
    dens = float(shapely.contains_xy(outline, pts[:, 0], pts[:, 1]).sum() / max(outline.area, 1.0))
    cover = support_area_m2 / max(wall.area, 1.0)
    shift = float(np.hypot(*(pts[:, :2].mean(0) - np.array(wall.centroid.coords[0]))) / math.sqrt(max(wall.area, 1.0))) if n else 0.0
    reasons = []
    if dens < p.density_refuse:
        reasons.append("lidar_too_sparse")
    elif dens < p.density_ok:
        reasons.append("low_density")
    if cover < p.mismatch_lo or cover > p.mismatch_hi or shift >= p.mismatch_shift:
        reasons.append("outline_mismatch")
    # fit_clear and tree_cover_pct are REPORTED only: a wrong drawn surface (flat over a slope, a merged plane) puts the
    # real roof returns "above" it, so a canopy-free fit would hide exactly the roofs the verdict must catch
    if (fit_all is not None and fit_all < p.fit_floor) or (supported_pct is not None and supported_pct < p.supported_floor):
        reasons.append("poor_fit")
    if parcel_match in ("street", "nearest"):
        reasons.append("not_exact_parcel")
    return Quality(verdict=reasons[0] if reasons else "ok", reasons=reasons, fit_all=fit_all, fit_covered=fit_cov,
                   coverage=cover_pts, supported_pct=supported_pct, density=round(dens, 1), outline_shift=round(shift, 3),
                   parcel_match=parcel_match, outline_source=provider, overhang_scale=overhang_scale,
                   roof_cover_of_outline=round(cover, 2), extra_roof_ring_ratio=None if extra is None else round(extra, 2),
                   tree_contact_pct=tree_pct, fit_clear=fit_clear, tree_cover_pct=tree_cover)


def tree_contact_pct(outline: Polygon, unassigned: np.ndarray) -> float:
    """Percent of the roof outline (sampled every 0.5 m) within 0.8 m of a roof point no plane explains."""
    samples = [outline.exterior.interpolate(t) for t in np.arange(0, outline.exterior.length, 0.5)]
    if not len(unassigned) or not samples:
        return 0.0
    dd, _ = cKDTree(unassigned[:, :2]).query(np.array([[s.x, s.y] for s in samples]), k=1)
    return round(float((dd < 0.8).mean() * 100), 1)


def ring_roof_extra_ratio(wide: np.ndarray | None, wall: Polygon, p: EngineParams) -> float | None:
    """Area of planar roof-height returns OUTSIDE the wall line (ring 1.2-6 m) that connect to the roof, divided by
    the wall-line area. ``wide`` is (m, 4) x, y, z, ASPRS class (world frame). None without usable ground."""
    if wide is None:
        return None
    w = np.asarray(wide, float)
    g = w[w[:, 3] == 2]
    if len(g) < 10:
        return None
    near = wall.buffer(6.0)
    sel = (shapely.contains_xy(near, w[:, 0], w[:, 1]) & ~shapely.contains_xy(wall.buffer(1.2), w[:, 0], w[:, 1])
           & (w[:, 3] != 2) & ~np.isin(w[:, 3], _NOT_ROOF_CLASSES))
    ring = w[sel]
    if len(ring) < 30:
        return 0.0
    _, ix = cKDTree(g[:, :2]).query(ring[:, :2], k=3)
    ring = ring[(ring[:, 2] - g[ix, 2].mean(1)) > 2.5]
    if len(ring) < 30:
        return 0.0
    nrm, curv, _ = knn_normals(ring[:, :3], p)
    pr = ring[(curv < 0.02) & (nrm[:, 2] > 0.6)]
    if len(pr) < 10:
        return 0.0
    cs = 0.5
    minx, miny, maxx, maxy = near.bounds
    nx, ny = int((maxx - minx) / cs) + 2, int((maxy - miny) / cs) + 2
    grid = np.zeros((ny, nx), bool)
    grid[((pr[:, 1] - miny) / cs).astype(int), ((pr[:, 0] - minx) / cs).astype(int)] = True
    grid = ndi.binary_closing(grid, iterations=1)
    gx, gy = np.meshgrid(minx + (np.arange(nx) + 0.5) * cs, miny + (np.arange(ny) + 0.5) * cs)
    roofcells = shapely.contains_xy(wall.buffer(1.4), gx, gy)
    lab, _ = ndi.label(grid | roofcells)
    touching = sorted(set(np.unique(lab[roofcells & (lab > 0)]).tolist()))
    comp = np.isin(lab, touching) & grid & ~roofcells
    return float(comp.sum() * cs * cs / max(wall.area, 1.0))
