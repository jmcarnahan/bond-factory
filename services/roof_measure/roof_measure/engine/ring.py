"""Ring filter: returns beside the building that cannot be roof (tree crowns, a neighbour's wall) are dropped before plane
detection, so 150 stray points at 1 m cannot turn a pitched roof flat or stretch the outline. Metres, building frame."""

from __future__ import annotations

from typing import Any

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

from .params import EngineParams


def ring_filter(crop: np.ndarray, wall: Polygon, p: EngineParams, diag: dict[str, Any]) -> np.ndarray:
    """Drop returns of the ring outside the footprint that cannot be roof: (1) higher than the roof just inside the
    footprint (the highest of its ``ring_k`` nearest inside returns) by more than ``ring_above_m`` (a tree crown or a
    neighbour's wall); (2) in a ``ring_cell_m`` cell whose returns span more than ``ring_span_m`` in height (a wall or a
    crown: a roof has one height per place). Points inside the footprint are never touched."""
    if not p.ring_filter or len(crop) < 20:
        return crop
    outside = ~shapely.contains_xy(wall.buffer(p.ring_guard_m), crop[:, 0], crop[:, 1])  # only beyond the guard
    inside = shapely.contains_xy(wall, crop[:, 0], crop[:, 1])
    if inside.sum() < p.ring_k or not outside.any():
        return crop
    tree = cKDTree(crop[inside, :2])
    k = min(p.ring_k, int(inside.sum()))
    _, nn = tree.query(crop[outside, :2], k=k)
    zmax = crop[inside, 2][np.atleast_2d(nn.reshape(int(outside.sum()), -1))].max(1)
    drop = np.zeros(len(crop), bool)
    drop[np.nonzero(outside)[0][crop[outside, 2] > zmax + p.ring_above_m]] = True
    cells = np.floor(crop[:, :2] / p.ring_cell_m).astype(np.int64)
    key = cells[:, 0] * 1_000_003 + cells[:, 1]
    order = np.argsort(key, kind="stable")
    ks, zs = key[order], crop[order, 2]
    starts = np.r_[0, np.nonzero(np.diff(ks))[0] + 1]
    zmin = np.minimum.reduceat(zs, starts)
    zmx = np.maximum.reduceat(zs, starts)
    tall = np.repeat(zmx - zmin > p.ring_span_m, np.diff(np.r_[starts, len(ks)]))
    span_drop = np.zeros(len(crop), bool)
    span_drop[order] = tall
    drop |= span_drop & outside
    diag["ring_dropped"] = int(drop.sum())
    return crop[~drop]
