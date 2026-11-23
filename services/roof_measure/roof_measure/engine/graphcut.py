"""Alpha-beta swap graph cut on a Potts model, with scipy's max-flow (own code; no GPL graph-cut library)."""

from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order, maximum_flow

from .errors import Ctx


def _swap_pair(a: int, b: int, di: np.ndarray, edges: np.ndarray, wi: np.ndarray, lab: np.ndarray) -> int:
    """Re-decide the cells labelled a or b by one min cut; returns the number of cells that changed."""
    m = len(lab)
    s_idx = np.nonzero((lab == a) | (lab == b))[0]
    if len(s_idx) < 2:
        return 0
    imap = -np.ones(m, int)
    imap[s_idx] = np.arange(len(s_idx))
    eu, ev = edges[:, 0], edges[:, 1]
    sel = (imap[eu] >= 0) & (imap[ev] >= 0)
    u, v, ww = imap[eu[sel]], imap[ev[sel]], wi[sel]
    n = len(s_idx)
    src, snk = n, n + 1
    rows = np.concatenate([u, v, np.full(n, src), np.arange(n)])
    cols = np.concatenate([v, u, np.arange(n), np.full(n, snk)])
    caps = np.concatenate([ww, ww, di[s_idx, b], di[s_idx, a]])
    cm = coo_matrix((caps.astype(np.int32), (rows, cols)), shape=(n + 2, n + 2)).tocsr()
    cm.sum_duplicates()
    res = maximum_flow(cm, src, snk)
    resid = (cm - res.flow).tocsr()
    resid.data = np.where(resid.data > 0, 1, 0).astype(np.int8)
    resid.eliminate_zeros()
    order = breadth_first_order(resid, src, directed=True, return_predecessors=False)
    reach = np.zeros(n + 2, bool)
    reach[order] = True
    newlab = np.where(reach[:n], a, b)
    changed = int((newlab != lab[s_idx]).sum())
    lab[s_idx] = newlab
    return changed


def graphcut_swap(cost: np.ndarray, edges: np.ndarray, w_edge: np.ndarray, lab: np.ndarray, ctx: Ctx) -> np.ndarray:
    """Alpha-beta swap on a Potts model. ``cost`` (cells, labels), ``edges`` (E, 2) cell pairs, ``w_edge`` (E,)."""
    p = ctx.p
    di = np.rint(cost * p.graphcut_scale).astype(np.int64)
    wi = np.maximum(np.rint(w_edge * p.graphcut_scale).astype(np.int64), 1)
    for _ in range(p.graphcut_rounds):
        la, lb = lab[edges[:, 0]], lab[edges[:, 1]]
        diff = la != lb
        pairs = {(min(x, y), max(x, y)) for x, y in zip(la[diff].tolist(), lb[diff].tolist(), strict=True)}
        changed = 0
        for a, b in sorted(pairs):
            ctx.check()
            changed += _swap_pair(a, b, di, edges, wi, lab)
        if changed == 0:
            break
    return lab
