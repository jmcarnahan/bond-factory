"""Label raster: cell grid over the roof outline, data costs per plane, ring tracing back to polygons. Metres."""

from __future__ import annotations

import math

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon

from .errors import Ctx
from .graphcut import graphcut_swap
from .params import EngineParams


def _trace_rings(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """Closed boundary rings (lattice corners, x = column, y = row) of the True cells of ``mask``."""
    pad = np.pad(mask, 1)
    m = pad[1:-1, 1:-1]
    below, above = ~pad[:-2, 1:-1], ~pad[2:, 1:-1]
    left, right = ~pad[1:-1, :-2], ~pad[1:-1, 2:]
    out: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def add(sel, f):
        ii, jj = np.nonzero(sel)
        for i, j in zip(ii.tolist(), jj.tolist(), strict=True):
            a, b = f(i, j)
            out.setdefault(a, []).append(b)

    add(m & below, lambda i, j: ((j, i), (j + 1, i)))
    add(m & right, lambda i, j: ((j + 1, i), (j + 1, i + 1)))
    add(m & above, lambda i, j: ((j + 1, i + 1), (j, i + 1)))
    add(m & left, lambda i, j: ((j, i + 1), (j, i)))
    rings = []
    for start in list(out.keys()):
        while out.get(start):
            ring = [start]
            cur = start
            prev_dir = None
            while True:
                cands = out.get(cur)
                if not cands:
                    break
                if len(cands) == 1 or prev_dir is None:
                    nxt = cands.pop(0)
                else:  # prefer the right turn (keeps diagonal cells separate)
                    best, bs = None, None
                    for c in cands:
                        d = (c[0] - cur[0], c[1] - cur[1])
                        s = -(prev_dir[0] * d[1] - prev_dir[1] * d[0])
                        if bs is None or s > bs:
                            bs, best = s, c
                    cands.remove(best)
                    nxt = best
                prev_dir = (nxt[0] - cur[0], nxt[1] - cur[1])
                cur = nxt
                if cur == start:
                    break
                ring.append(cur)
            if len(ring) >= 4:
                rings.append(ring)
    return rings


def trace_polys(mask: np.ndarray, x0: float, y0: float, h: float) -> list[Polygon]:
    """Boolean mask (ny, nx; row = y) to polygons whose vertices are all lattice corners, so neighbouring
    labels share identical vertices. Cell (i, j) spans [x0 + j*h, x0 + (j+1)*h] x [y0 + i*h, y0 + (i+1)*h]."""
    shells, holes = [], []
    for r in _trace_rings(mask):
        a = np.array(r, float)
        area = 0.5 * np.sum(a[:, 0] * np.roll(a[:, 1], -1) - np.roll(a[:, 0], -1) * a[:, 1])
        pts = [(x0 + q[0] * h, y0 + q[1] * h) for q in r]
        (shells if area > 0 else holes).append((abs(area), pts))
    sp = [Polygon(s[1]) for s in shells]
    hole_of: dict[int, list] = {i: [] for i in range(len(sp))}
    for hz in holes:
        hp = Point(hz[1][0])
        best = None
        for i, s in enumerate(sp):
            hit = s.area > hz[0] and s.contains(Point(hz[1][1][0] + 1e-9, hz[1][1][1] + 1e-9)) or s.covers(hp)
            if hit and (best is None or s.area < sp[best].area):
                best = i
        if best is not None:
            hole_of[best].append(hz[1])
    return [Polygon(s[1], hole_of[i]) for i, s in enumerate(shells)]


def grid_domain(outline: Polygon, h: float) -> tuple[float, float, int, int, np.ndarray, np.ndarray]:
    """Cell grid over the outline's bounds plus a 3-cell margin: (minx, miny, nx, ny, X, Y) of the cell centres."""
    minx, miny, maxx, maxy = outline.bounds
    minx -= 3 * h
    miny -= 3 * h
    nx = math.ceil((maxx + 3 * h - minx) / h)
    ny = math.ceil((maxy + 3 * h - miny) / h)
    xs = minx + (np.arange(nx) + 0.5) * h
    ys = miny + (np.arange(ny) + 0.5) * h
    gx, gy = np.meshgrid(xs, ys)
    return minx, miny, nx, ny, gx, gy


def data_costs(cells: np.ndarray, q: np.ndarray, qlab: np.ndarray, planes: list, p: EngineParams) -> np.ndarray:
    """Cost (cells, planes) of giving each cell centre to each plane, from the inlier points ``q`` and their labels."""
    m, k = len(cells), len(planes)
    tree = cKDTree(q[:, :2])
    d, idx = tree.query(cells, k=p.cost_nbrs, distance_upper_bound=p.cost_radius_m)
    valid = np.isfinite(d)
    idx2 = np.where(valid, idx, 0)
    w = np.exp(-(d / p.cost_sigma_m) ** 2) * valid
    wsum = w.sum(1) + 1e-3
    cost = np.zeros((m, k))
    for lab in range(k):
        pl = planes[lab]
        res = np.abs(q[idx2, 2] - (pl[0] * q[idx2, 0] + pl[1] * q[idx2, 1] + pl[2]))
        r = np.minimum(res / p.cost_tau_m, 1.0)
        mism = (qlab[idx2] != lab).astype(float)
        wl = p.cost_label_weight
        cost[:, lab] = ((wl * mism + (1 - wl) * r) * w).sum(1) / wsum
        ql = q[qlab == lab]
        dl = cKDTree(ql[:, :2]).query(cells, k=1)[0] if len(ql) else np.full(m, 9.0)
        cost[:, lab] += p.cost_lambda * np.minimum(dl / p.cost_support_dist_m, 1.0)
    return cost


def _grid_edges(idx: np.ndarray, beta: float) -> tuple[np.ndarray, np.ndarray]:
    """8-neighbour edges between domain cells and their Potts weights (diagonals weigh 0.7071)."""
    ny, nx = idx.shape
    es, ws = [], []
    for di, dj, wt in [(0, 1, 1.0), (1, 0, 1.0), (1, 1, 0.7071), (1, -1, 0.7071)]:
        if di == 0:
            a, b = idx[:, :nx - dj], idx[:, dj:]
        elif dj >= 0:
            a = idx[:ny - di, :nx - dj] if dj > 0 else idx[:ny - di, :]
            b = idx[di:, dj:] if dj > 0 else idx[di:, :]
        else:
            a, b = idx[:ny - di, -dj:], idx[di:, :nx + dj]
        m = (a >= 0) & (b >= 0)
        es.append(np.c_[a[m], b[m]])
        ws.append(np.full(m.sum(), wt * beta))
    return np.vstack(es), np.concatenate(ws)


def label_raster(outline: Polygon, q: np.ndarray, qlab: np.ndarray, planes: list, h: float, beta: float,
                 ctx: Ctx) -> tuple[np.ndarray, tuple[float, float, float]]:
    """Global labelling of the outline's cells: data cost + Potts smoothness, solved by alpha-beta swaps.

    Returns (label raster, -1 outside the outline, and the grid origin ``(minx, miny, h)``)."""
    minx, miny, _, _, gx, gy = grid_domain(outline, h)
    dom = shapely.contains_xy(outline.buffer(0.10), gx, gy)
    idx = -np.ones(dom.shape, int)
    idx[dom] = np.arange(dom.sum())
    cells = np.c_[gx[dom], gy[dom]]
    cost = data_costs(cells, q, qlab, planes, ctx.p)
    lab = cost.argmin(1)
    edges, w_edge = _grid_edges(idx, beta)
    lab = graphcut_swap(cost, edges, w_edge, lab.copy(), ctx)
    out = -np.ones(dom.shape, int)
    out[dom] = lab
    return out, (minx, miny, h)
