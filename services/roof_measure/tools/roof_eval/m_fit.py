"""Point-based metrics: how well the facets explain the frozen reference roof points. None reads the engine's outline."""

from __future__ import annotations

import numpy as np

from .geom import M2_TO_SQFT, UNCOUNTED_EDGE_TYPES, Roof, surface_points
from .seam_check import strip_step

FIT_TOL_M = 0.15
FALSE_JUMP_M = 0.3  # contract-0.4: a level_change is a jump >= 0.3 m, so a measured jump below this is false
SIDE_NEAR_M, SIDE_FAR_M, SIDE_MIN_PTS = 0.2, 1.5, 5
CLOSE_M = 0.3  # facets are meant to tile: a gap narrower than this between facets is a tiling defect


def assign(roof: Roof, ref: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(facet index per reference point, vertical residual to that facet's plane; NaN where in no facet)."""
    idx = surface_points(roof, ref[:, :2]) if len(ref) else np.zeros(0, int)
    dz = np.full(len(ref), np.nan)
    for i, f in enumerate(roof.facets):
        m = idx == i
        if m.any():
            dz[m] = ref[m, 2] - f.z_at(ref[m, 0], ref[m, 1])
    return idx, dz


def fit_all(roof: Roof, ref: np.ndarray, tol: float = FIT_TOL_M) -> float | None:
    """Share of ALL reference points within ``tol`` metres vertically of the plane of the facet containing them.
    A point in no facet is a miss. None when there are no reference points."""
    if len(ref) == 0:
        return None
    _, dz = assign(roof, ref)
    return float(np.sum(np.abs(np.nan_to_num(dz, nan=np.inf)) <= tol) / len(ref))


def fit_covered(roof: Roof, ref: np.ndarray, tol: float = FIT_TOL_M) -> float | None:
    """Share of the reference points that lie inside some facet and are within ``tol`` of that facet's plane.
    None when no point is covered."""
    _, dz = assign(roof, ref)
    ok = ~np.isnan(dz)
    return float(np.mean(np.abs(dz[ok]) <= tol)) if ok.any() else None


def coverage(roof: Roof, ref: np.ndarray) -> float | None:
    """Share of the reference points that fall inside any facet (plan view)."""
    if len(ref) == 0:
        return None
    idx, _ = assign(roof, ref)
    return float(np.mean(idx >= 0))


def overlap_sqft(roof: Roof) -> float:
    """Sum over facet pairs of the plan area where two facets overlap (square feet; touching edges count zero)."""
    ps = [f.poly for f in roof.facets]
    total = 0.0
    for i in range(len(ps)):
        for j in range(i + 1, len(ps)):
            if ps[i].bounds[2] < ps[j].bounds[0] or ps[j].bounds[2] < ps[i].bounds[0] \
                    or ps[i].bounds[3] < ps[j].bounds[1] or ps[j].bounds[3] < ps[i].bounds[1]:
                continue
            a = ps[i].intersection(ps[j]).area
            if a > 1e-6:
                total += a
    return total * M2_TO_SQFT


def tiling_gap_sqft(roof: Roof, close_m: float = CLOSE_M) -> float:
    """Plan area (sqft) of slivers and holes narrower than ``close_m`` between facets: the area added by a
    morphological closing of the facet union. Independent of the engine's outline."""
    u = roof.union
    if u.is_empty:
        return 0.0
    closed = u.buffer(close_m, join_style="mitre").buffer(-close_m, join_style="mitre")
    return max(0.0, closed.area - u.area) * M2_TO_SQFT


def outline_gap_sqft(roof: Roof) -> float | None:
    """Plan area (sqft) of the engine's own roof outline not covered by facets (reported, not gated on)."""
    if roof.outline.is_empty:
        return None
    return roof.outline.difference(roof.union).area * M2_TO_SQFT


def edge_jump_m(ref: np.ndarray, p0, p1) -> float | None:
    """Height jump across an edge measured from the reference points only: each side's local linear fit
    (z on across- and along-edge distance, points 0.2-1.5 m from the line) is evaluated on the line itself.
    None when either side has fewer than 5 points in the edge's span."""
    d = np.array([p1[0] - p0[0], p1[1] - p0[1]], float)
    ln = float(np.hypot(*d))
    if ln < 0.3 or len(ref) == 0:
        return None
    t, n = d / ln, np.array([-d[1], d[0]]) / ln
    rel = ref[:, :2] - np.array(p0[:2])
    u, s = rel @ t, rel @ n
    in_span = (u >= 0) & (u <= ln)
    z_at_line = []
    for sign in (1, -1):
        m = in_span & (sign * s >= SIDE_NEAR_M) & (sign * s <= SIDE_FAR_M)
        if m.sum() < SIDE_MIN_PTS:
            return None
        cols = [np.ones(m.sum()), s[m]] + ([u[m] - ln / 2] if np.ptp(u[m]) > 1.0 else [])
        coef = np.linalg.lstsq(np.stack(cols, 1), ref[m, 2], rcond=None)[0]
        z_at_line.append(coef[0])
    return abs(z_at_line[0] - z_at_line[1])


def false_level_change(roof: Roof, ref: np.ndarray) -> dict[str, float | int | None]:
    """The ENGINE'S level_change edges whose jump, measured from the points on both sides, is under 0.3 m (the contract
    threshold). ``share`` = their length over the total engine edge length; ``false_ft`` their feet; ``unverified`` counts
    edges with too few points to measure (not counted as false and not as correct)."""
    total = sum(e.length_ft for e in roof.engine_edges if e.type not in UNCOUNTED_EDGE_TYPES)
    bad_len, bad, unver, n = 0.0, 0, 0, 0
    fl = {f.id: f for f in roof.facets}
    for e in roof.engine_edges:
        if e.type != "level_change":
            continue
        n += 1
        pair = [fl[i] for i in e.facets if i in fl][:2] if len(e.facets) >= 2 else []
        if len(pair) == 2 and all(f.is_flat for f in pair):  # flat/flat: strip medians, independent of the engine's rule
            step = strip_step(ref, pair[0].poly, pair[1].poly, e.p0, e.p1)
            if step is None:
                unver += 1
            elif not step:
                bad += 1
                bad_len += e.length_ft
            continue
        j = edge_jump_m(ref, e.p0, e.p1)
        if j is None:
            unver += 1
        elif j < FALSE_JUMP_M:
            bad += 1
            bad_len += e.length_ft
    return {"share": bad_len / total if total > 0 else None, "count": bad, "unverified": unver, "edges": n, "false_ft": bad_len}


def unsupported_share(roof: Roof, ref: np.ndarray, radius: float = 0.5, cell: float = 0.25) -> float | None:
    """Precision: share of the drawn facet plan area (sampled every 0.25 m) with no reference point within 0.5 m.
    Facets drawn over nothing (hulls, padding, invented strips) score high. None without facets."""
    import shapely
    from scipy.spatial import cKDTree

    if not roof.facets:
        return None
    tree = cKDTree(ref[:, :2]) if len(ref) else None
    tot = bad = 0
    for f in roof.facets:
        minx, miny, maxx, maxy = f.poly.bounds
        gx, gy = np.meshgrid(np.arange(minx + cell / 2, maxx, cell), np.arange(miny + cell / 2, maxy, cell))
        gx, gy = gx.ravel(), gy.ravel()
        inside = shapely.contains_xy(f.poly, gx, gy)
        pts = np.c_[gx[inside], gy[inside]]
        tot += len(pts)
        bad += len(pts) if tree is None else int(np.sum(tree.query(pts, k=1)[0] > radius)) if len(pts) else 0
    return bad / tot if tot else None


def outside_outline_share(roof: Roof, foot, buffer: float = 1.5) -> float | None:
    """Share of the facet union's plan area that lies outside the wall outline buffered by 1.5 m."""
    u = roof.union
    if u.is_empty or foot is None or foot.is_empty or u.area <= 0:
        return None
    return u.difference(foot.buffer(buffer)).area / u.area
