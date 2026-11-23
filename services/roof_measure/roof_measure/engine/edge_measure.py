"""Measurements the edge typer needs from the points: the height jump across a line, the height profile that tells a
ridge or valley from a step, and straight pieces of a line. Metres in a local metric frame."""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from .plane_math import zat
from .types import Facet

SIDE_NEAR_M, SIDE_FAR_M, SIDE_MIN_PTS = 0.2, 1.5, 5  # the harness's measurement (tools.roof_eval.m_fit.edge_jump_m)


def points_jump(q: np.ndarray, p0: np.ndarray, p1: np.ndarray) -> float | None:
    """Height jump across the line p0-p1 from the points alone: each side's local linear fit (z on across- and
    along-line distance, points 0.2-1.5 m from the line, inside the segment's span) evaluated ON the line.
    None when the segment is under 0.3 m or either side has under 5 points. Same rule as the harness."""
    d = p1 - p0
    ln = float(np.hypot(*d))
    if ln < 0.3 or q is None or len(q) == 0:
        return None
    t, n = d / ln, np.array([-d[1], d[0]]) / ln
    rel = q[:, :2] - p0
    u, s = rel @ t, rel @ n
    in_span = (u >= 0) & (u <= ln)
    z_line = []
    for sign in (1, -1):
        m = in_span & (sign * s >= SIDE_NEAR_M) & (sign * s <= SIDE_FAR_M)
        if m.sum() < SIDE_MIN_PTS:
            return None
        cols = [np.ones(m.sum()), s[m]] + ([u[m] - ln / 2] if np.ptp(u[m]) > 1.0 else [])
        z_line.append(np.linalg.lstsq(np.stack(cols, 1), q[m, 2], rcond=None)[0][0])
    return abs(z_line[0] - z_line[1])


def measured_jump(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, q: np.ndarray | None) -> float:
    """Height jump (m) across p0-p1: measured from the points (``points_jump``); when a side has too few points to
    measure, the gap between the two planes at the middle of the line."""
    j = points_jump(q, p0, p1) if q is not None else None
    if j is not None:
        return float(j)
    if q is not None and len(q):  # points exist but a side is too thin: the jump cannot be verified, so it is not called a level change
        return 0.0
    mid = (p0 + p1) / 2
    return abs(zat(fa.plane, *mid) - zat(fb.plane, *mid))


def seg_split(line: BaseGeometry) -> list[tuple[np.ndarray, np.ndarray]]:
    """Straight pieces (a, b) of a (multi)linestring, dropping zero-length ones."""
    segs = []
    for g in (list(line.geoms) if hasattr(line, "geoms") else [line]):
        if g.geom_type != "LineString":
            continue
        c = np.array(g.coords)
        for i in range(len(c) - 1):
            if np.hypot(*(c[i + 1] - c[i])) > 1e-4:
                segs.append((c[i], c[i + 1]))
    return segs


def ridge_check(a: np.ndarray, b: np.ndarray, q: np.ndarray) -> str | None:
    """Height profile across a typed step: 'ridge' / 'valley' when the points peak (dip) at the line without a jump."""
    d = b - a
    length = float(np.hypot(*d))
    if length < 0.8:
        return None
    u = d / length
    n = np.array([-u[1], u[0]])
    rel = q[:, :2] - a
    along, perp = rel @ u, rel @ n
    m = (along > 0.2) & (along < length - 0.2)
    near = m & (np.abs(perp) < 0.45)
    far_p = m & (perp > 0.9) & (perp < 1.7)
    far_n = m & (perp < -0.9) & (perp > -1.7)
    if near.sum() < 5 or far_p.sum() < 4 or far_n.sum() < 4:
        return None
    zn = q[near, 2]
    design = np.c_[along[near], np.ones(near.sum())]
    res = zn - design @ np.linalg.lstsq(design, zn, rcond=None)[0]  # slope along the line removed
    if res.std() > 0.14:
        return None
    zf1, zf2, zz = q[far_p, 2].mean(), q[far_n, 2].mean(), zn.mean()
    if zz > max(zf1, zf2) + 0.05 and abs(zf1 - zf2) < 0.6:
        return "ridge"
    if zz < min(zf1, zf2) - 0.05 and abs(zf1 - zf2) < 0.6:
        return "valley"
    return None


REF_MIN_HEIGHT_M = 1.5  # the harness's reference-point rule (tools.roof_eval.data.derive_reference, ref-v1)
REF_BUFFER_M = 1.2
NON_ROOF_CLASSES = (2, 3, 4, 5, 7, 9)  # ground, vegetation, noise, water


def jump_points(wide: np.ndarray | None, wall: BaseGeometry) -> np.ndarray | None:
    """The points level changes are measured from: every return of the wide cloud (x, y, z, ASPRS class) that is not
    ground, vegetation, noise or water, stands more than 1.5 m above the local ground (median of its 6 nearest ground
    returns) and lies within 1.2 m of the wall outline. This is the harness's reference rule, so the engine and the
    harness measure the same jump. None without a wide cloud or without ground to measure height from."""
    from scipy.spatial import cKDTree

    if wide is None or len(wide) == 0:
        return None
    w = np.asarray(wide, float)
    g = w[w[:, 3] == 2]
    if len(g) < 6:
        return None
    c = w[~np.isin(w[:, 3], NON_ROOF_CLASSES)][:, :3]
    _, i = cKDTree(g[:, :2]).query(c[:, :2], k=6)
    c = c[c[:, 2] - np.median(g[i, 2], axis=1) > REF_MIN_HEIGHT_M]
    return c[shapely.intersects_xy(wall.buffer(REF_BUFFER_M), c[:, 0], c[:, 1])]
