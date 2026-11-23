"""Region growing of planes over a roof point cloud, plane assignment and refitting. Metres."""

from __future__ import annotations

import math

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from .errors import Ctx
from .params import EngineParams
from .plane_math import fit_plane, pdist


def _unit_normal(plane) -> np.ndarray:
    nrm = np.array([-plane[0], -plane[1], 1.0])
    return nrm / np.linalg.norm(nrm)


def region_grow(pts: np.ndarray, normals: np.ndarray, curv: np.ndarray, tree: cKDTree,
                ctx: Ctx) -> tuple[np.ndarray, list]:
    """Grow planar regions from the flattest points first. Returns (label per point, -1 unassigned; planes)."""
    p = ctx.p
    n = len(pts)
    lab = np.full(n, -1, int)
    _, nbr = tree.query(pts, k=p.grow_nbrs + 1)
    cosang = math.cos(math.radians(p.grow_angle_deg))
    order = np.argsort(curv, kind="stable")
    planes: list = []
    for count, s in enumerate(order):
        if count & 127 == 0:
            ctx.check()
        if lab[s] != -1 or normals[s, 2] == 0:
            continue
        ii = [j for j in nbr[s] if lab[j] == -1]
        if len(ii) < p.grow_seed_min:
            continue
        pl = fit_plane(pts[ii])
        nrm = _unit_normal(pl)
        members = [s]
        lab[s] = -2
        queue = [s]
        qi = 0
        nfit = 1
        while qi < len(queue):
            c = queue[qi]
            qi += 1
            for j in nbr[c]:
                if lab[j] != -1:
                    continue
                if normals[j] @ nrm < cosang:
                    continue
                if pdist(pl, pts[j:j + 1])[0] > p.grow_dist_m:
                    continue
                lab[j] = -2
                members.append(j)
                queue.append(j)
                if len(members) >= max(p.grow_refit_min, p.grow_refit_factor * nfit):
                    pl = fit_plane(pts[members])
                    nfit = len(members)
                    nrm = _unit_normal(pl)
        if len(members) >= p.grow_min_pts:
            planes.append(fit_plane(pts[members]))
            lab[members] = len(planes) - 1
        else:
            lab[members] = -3
    lab[lab < 0] = -1
    return lab, planes


def assign(pts: np.ndarray, planes: list, tol: float) -> np.ndarray:
    """Label each point with its nearest plane when within ``tol`` metres, else -1."""
    if not planes:
        return np.full(len(pts), -1)
    dist = np.stack([pdist(pl, pts) for pl in planes], 1)
    j = dist.argmin(1)
    ok = dist[np.arange(len(pts)), j] < tol
    return np.where(ok, j, -1)


def drop_islands(pts: np.ndarray, lab: np.ndarray, planes: list, p: EngineParams) -> np.ndarray:
    """Unlabel small scattered islands: points of one plane that are not within ``assign_link_m`` (plan view) of the
    plane's main body, number between ``assign_island_min_pts`` and ``assign_island_pts`` (a handful of strays at a
    crease are not a crown) and do not lie flat on the plane (residual rms above
    the larger of ``assign_island_rms_m`` and ``assign_island_noise_x`` times the main body's own rms). A plane is infinite, so a tree crown or a chimney return that happens to lie within the
    tolerance of a roof plane would otherwise join it (and bend the plane, grow the outline); a small separate part
    that IS planar (a porch hip end coplanar with the main slope) is a real facet and stays."""
    out = lab.copy()
    for i in np.unique(lab[lab >= 0]):
        idx = np.nonzero(lab == i)[0]
        if len(idx) < 2:
            continue
        pairs = cKDTree(pts[idx, :2]).query_pairs(p.assign_link_m, output_type="ndarray")
        if len(pairs) == 0:
            ncomp, comp = len(idx), np.arange(len(idx))
        else:
            g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(idx), len(idx)))
            ncomp, comp = connected_components(g, directed=False)
        if ncomp == 1:
            continue
        sizes = np.bincount(comp)
        main = int(sizes.argmax())
        thr = max(p.assign_island_rms_m, p.assign_island_noise_x * float(pdist(planes[i], pts[idx[comp == main]]).std()))
        for c in range(ncomp):
            if c == main or sizes[c] >= p.assign_island_pts or sizes[c] < p.assign_island_min_pts:
                continue
            sel = idx[comp == c]
            if float(pdist(planes[i], pts[sel]).std()) > thr:
                out[sel] = -1
    return out


def refit(pts: np.ndarray, lab: np.ndarray, planes: list, p: EngineParams, tol: float | None = None,
          iters: int = 4) -> tuple[np.ndarray, list]:
    """Alternate plane refits (planes with >= ``refit_min_pts`` members) and reassignment."""
    tol = p.refit_tol_m if tol is None else tol
    planes = [np.array(q, float) for q in planes]
    for _ in range(iters):
        for i in range(len(planes)):
            m = lab == i
            if m.sum() >= p.refit_min_pts:
                planes[i] = fit_plane(pts[m])
        lab = assign(pts, planes, tol)
    return lab, planes
