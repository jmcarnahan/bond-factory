"""Cost-sheet totals and quality signals with the verdict (plan 3.1 key names, plan 3.9 thresholds).

Everything here works in whatever metric frame the facets are in; areas are square feet, lengths feet.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

from .normals import knn_normals
from .params import EngineParams
from .types import Facet, Quality

_NOT_ROOF_CLASSES = [3, 4, 5, 7, 9]  # ASPRS vegetation, noise, water classes: never roof


def _fit_shares(facets: list[Facet], pts: np.ndarray, near: np.ndarray, p: EngineParams
                ) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """(fit_all, fit_covered, coverage, fit_clear, tree_cover_pct): coverage over all roof returns ``pts``, the others
    over the returns ``near`` the drawn roof (a mask over ``pts``). One containment pass.

    fit_all: share within ``fit_tol_m`` of the plane of the facet they fall in (a return outside every facet counts as
    a miss). fit_covered: the same over the returns inside a facet. Canopy: a return more than ``canopy_above_m`` ABOVE
    the surface under it (inside a facet, or outside one but within 2 m of it: the surface there is that facet's
    plane): trees over the eaves, not roof. fit_clear is fit_all with the canopy left out of the count (reported, not
    part of the verdict); tree_cover_pct the canopy's share. Returns far BELOW the surface or off it stay misses."""
    n_all = len(pts)
    assigned = np.full(n_all, -1)
    for i, f in enumerate(facets):
        c = shapely.contains_xy(f.polygon, pts[:, 0], pts[:, 1])
        assigned[(assigned < 0) & c] = i
    coverage = round(float((assigned >= 0).mean()), 3) if n_all else None
    pts, assigned = pts[near], assigned[near]
    n = len(pts)
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
        near_f = d.argmin(0)
        close = d.min(0) <= 2.0
        for i, f in enumerate(facets):
            m = close & (near_f == i)
            if m.any():
                pl = f.plane
                r = pts[out[m], 2] - (pl[0] * pts[out[m], 0] + pl[1] * pts[out[m], 1] + pl[2])
                canopy[out[m][r > p.canopy_above_m]] = True
    fit_all = round(float(ok.sum() / n), 3) if n else None
    fit_cov = round(float(ok.sum() / ins.sum()), 3) if ins.sum() else None
    clear_n = n - int(canopy.sum())
    fit_clear = round(float(ok.sum() / clear_n), 3) if clear_n > 0 else None
    tree = round(100.0 * float(canopy.mean()), 1) if n else None
    return fit_all, fit_cov, coverage, fit_clear, tree


# The closed list of quality reasons, most serious first. The verdict is the most serious reason present ("ok" when
# none). A SOFT verdict (the roof is drawn as measured; the caller only needs to know) is replaced by any serious
# reason, so a low density or a nearest-parcel match never hides a wrong outline or a poor fit.
REASONS = ("lidar_too_sparse", "outline_mismatch", "poor_fit", "planes_not_found", "outline_no_evidence",
           "roof_continues", "roof_part_missed", "low_density", "not_exact_parcel")
SOFT = ("ok", "not_exact_parcel", "low_density")
_VERDICT_WORD = {"planes_not_found": "poor_fit"}  # the verdict a reader already knows for a roof drawn from no planes


def verdict_of(reasons: list[str]) -> str:
    """The verdict for ``reasons``: the most serious one in REASONS order, "ok" when there is none."""
    known = [r for r in reasons if r in REASONS]
    if not known:
        return "ok"
    worst = min(known, key=REASONS.index)
    return _VERDICT_WORD.get(worst, worst)


def add_reason(q: Quality, reason: str) -> None:
    """Append ``reason`` once and recompute the verdict."""
    if reason not in q.reasons:
        q.reasons.append(reason)
    q.verdict = verdict_of(q.reasons)


def quality(facets: list[Facet], pts: np.ndarray, outline: Polygon, wall: Polygon, parcel_match: str | None,
            provider: str, supported_pct: float | None, support_area_m2: float,
            extra: float | None, tree_pct: float | None, p: EngineParams, diag: dict | None = None) -> Quality:
    """Plan 3.9 signals and verdict. ``pts`` are all roof points in the frame of the facets (the crop round the given
    wall line). The fit shares are taken over the returns inside the drawn roof outline grown by
    ``fit_outline_margin_m``: they say how well the planes describe THIS roof, not how many returns of a neighbour's roof,
    a wall or a tree the wall-line crop caught. ``coverage`` stays over all of ``pts``."""
    near = shapely.contains_xy(outline.buffer(p.fit_outline_margin_m), pts[:, 0], pts[:, 1]) if len(pts) else np.zeros(0, bool)
    fit_all, fit_cov, cover_pts, fit_clear, tree_cover = _fit_shares(facets, pts, near, p)
    n = len(pts)
    dens = float(shapely.contains_xy(outline, pts[:, 0], pts[:, 1]).sum() / max(outline.area, 1.0))
    cover = support_area_m2 / max(wall.area, 1.0)
    d = diag or {}
    # against the GIVEN wall, on purpose: the points are the crop round it, so their centre sits between the given and
    # the registered wall and the registered centre read higher (160 houses: two ok houses 0.05 -> 0.12); the normal
    # 0.8-0.9 m registration keeps every tuning house under mismatch_shift (max 0.165)
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
    if d.get("edge_no_evidence_share", 0.0) >= p.no_evidence_share:
        reasons.append("outline_no_evidence")  # part of the outline has no roof returns at all: drawn from the wall line
    if d.get("edge_end_share", 0.0) >= p.roof_continues_share:
        reasons.append("roof_continues")  # the roof plane carries on past the outline: an attached roof left out
    return Quality(verdict=verdict_of(reasons), reasons=reasons, fit_all=fit_all, fit_covered=fit_cov,
                   coverage=cover_pts, supported_pct=supported_pct, density=round(dens, 1), outline_shift=round(shift, 3),
                   parcel_match=parcel_match, outline_source=provider,
                   roof_cover_of_outline=round(cover, 2), extra_roof_ring_ratio=None if extra is None else round(extra, 2),
                   tree_contact_pct=tree_pct, fit_clear=fit_clear, tree_cover_pct=tree_cover)


def part_missed_reason(roof_part_missed_sqft: float, p: EngineParams) -> str | None:
    """``roof_part_missed`` when the objects step found planar roof the facets left out (only blobs over 3 m2 are
    counted there) of at least ``part_missed_min_sqft``; None otherwise. For the step that knows the figure."""
    return "roof_part_missed" if roof_part_missed_sqft >= p.part_missed_min_sqft else None


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
