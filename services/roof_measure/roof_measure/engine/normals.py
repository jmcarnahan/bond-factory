"""Local surface normals of a roof point cloud (k nearest neighbours, eigen-decomposition). Metres."""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from .params import EngineParams


def knn_normals(pts: np.ndarray, p: EngineParams) -> tuple[np.ndarray, np.ndarray, cKDTree]:
    """Per point: unit normal (z up; zero when under-supported), curvature (smallest eigenvalue share), and the tree."""
    n = len(pts)
    tree = cKDTree(pts)
    d, idx = tree.query(pts, k=p.knn_k, distance_upper_bound=p.knn_radius_m)
    valid = np.isfinite(d)
    idx2 = np.where(valid, idx, np.arange(n)[:, None])
    q = pts[idx2]
    w = valid[..., None].astype(float)
    cnt = np.maximum(valid.sum(1), 1)
    mean = (q * w).sum(1) / cnt[:, None]
    qc = (q - mean[:, None]) * w
    cov = np.einsum("nki,nkj->nij", qc, qc)
    ev, evec = np.linalg.eigh(cov)
    nrm = evec[:, :, 0].copy()
    nrm[nrm[:, 2] < 0] *= -1
    curv = ev[:, 0] / np.maximum(ev.sum(1), 1e-9)
    weak = valid.sum(1) < p.knn_min_valid
    nrm[weak] = 0
    curv[weak] = 1
    return nrm, curv, tree
