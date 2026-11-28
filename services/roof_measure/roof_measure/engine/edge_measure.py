"""Measurements the edge typer needs from the points: the height jump across a line, the height profile that tells a
ridge or valley from a step, and straight pieces of a line. Metres in a local metric frame."""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from .params import EngineParams
from .plane_math import zat
from .types import Facet

SIDE_NEAR_M, SIDE_FAR_M, SIDE_MIN_PTS = 0.2, 1.5, 5  # the harness's measurement (tools.roof_eval.m_fit.edge_jump_m)


def _line_height(s: np.ndarray, u: np.ndarray, z: np.ndarray, ln: float, trim_m: float) -> float | None:
    """Height on the line (s = 0, middle of the span) of the local linear fit of z on across-line (and along-line, when the
    returns spread over more than a metre of it) distance. A robust fit: after the first fit the returns further from it than
    ``trim_m`` or 3 robust sigmas (a canopy that is only partly over the limit) are left out and it is fitted again."""
    for second in (False, True):
        if len(z) < SIDE_MIN_PTS:
            return None
        cols = [np.ones(len(z)), s] + ([u - ln / 2] if np.ptp(u) > 1.0 else [])
        design = np.stack(cols, 1)
        coef = np.linalg.lstsq(design, z, rcond=None)[0]
        if second:
            break
        res = z - design @ coef
        good = np.abs(res) <= max(trim_m, 3.0 * 1.4826 * float(np.median(np.abs(res - np.median(res)))))
        if good.all():
            break
        s, u, z = s[good], u[good], z[good]
    return float(coef[0])


def points_jump(q: np.ndarray, p0: np.ndarray, p1: np.ndarray, plane_pos: np.ndarray, plane_neg: np.ndarray,
                p: EngineParams) -> float | None:
    """Height jump across the line p0-p1 from the points: each side's local linear fit (z on across- and along-line distance,
    points 0.2-1.5 m from the line, inside the segment's span) evaluated ON the line. ``plane_pos`` is the plane of the facet
    on the left of p0 -> p1 (the +normal side), ``plane_neg`` the other: a return more than ``p.jump_outlier_m`` off its own
    side's plane (a tree over the seam) is not measured, and the fit is trimmed (``_line_height``). Everything is relative to
    p0, so a roof moved as a whole gives the same answer. None when the segment is under 0.3 m or a side has under 5 returns."""
    d = p1 - p0
    ln = float(np.hypot(*d))
    if ln < 0.3 or q is None or len(q) == 0:
        return None
    t, n = d / ln, np.array([-d[1], d[0]]) / ln
    rel = q[:, :2] - p0
    u, s = rel @ t, rel @ n
    in_span = (u >= 0) & (u <= ln)
    z_line = []
    for sign, plane in ((1, plane_pos), (-1, plane_neg)):
        m = in_span & (sign * s >= SIDE_NEAR_M) & (sign * s <= SIDE_FAR_M)
        if m.sum() < SIDE_MIN_PTS:
            return None
        own = np.abs(zat(plane, q[m, 0], q[m, 1]) - q[m, 2]) <= p.jump_outlier_m
        h = _line_height(s[m][own], u[m][own], q[m, 2][own], ln, p.jump_trim_m)
        if h is None:
            return None
        z_line.append(h)
    return abs(z_line[0] - z_line[1])


def crease_slope(plane_a: np.ndarray, plane_b: np.ndarray) -> float:
    """Slope (rise over plan run) of the line where two planes meet: it does not depend on where a partition happens to
    draw the shared boundary. 0 for planes with the same gradient (parallel: they meet nowhere)."""
    (a1, b1, _), (a2, b2, _) = plane_a, plane_b
    run = float(np.hypot(b2 - b1, a1 - a2))
    return abs(a1 * b2 - b1 * a2) / run if run > 1e-9 else 0.0


# Seam rule constants (0.5.1). They are OUTSIDE the params hash: a retune MUST bump PIPELINE_VERSION (it keys the result cache).
# The 0.3 m offset is the same quantity as ``EngineParams.level_change_m`` (a height difference that makes a level change); the
# typer passes that value in, ``SEAM_LEVEL_M`` is only the default of a direct call.
SEAM_STEP_M, SEAM_MIN_STATIONS = 0.5, 12  # stations along a flat/flat seam: at most this far apart, at least this many
SEAM_LEVEL_M, SEAM_LEVEL_SHARE = 0.30, 0.70  # plane offset at or above this on at least this share of the stations


def seam_offsets(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray) -> np.ndarray:
    """The PLANE OFFSET d(p) = |zA(p) - zB(p)| (m) of the two facets' fitted planes (tilt included) at stations along the
    seam p0-p1: at least ``SEAM_MIN_STATIONS`` of them, never more than ``SEAM_STEP_M`` apart (the typer absorbs seams under
    1 m before this matters)."""
    ln = float(np.hypot(*(p1 - p0)))
    n = max(SEAM_MIN_STATIONS, int(np.ceil(ln / SEAM_STEP_M)) + 1)
    pts = p0 + np.linspace(0.0, 1.0, n)[:, None] * (p1 - p0)
    return np.array([abs(zat(fa.plane, x, y) - zat(fb.plane, x, y)) for x, y in pts])


def seam_is_level(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, level_m: float | None = None) -> tuple[bool, float]:
    """(is it a real step, median plane offset in m) for a seam between two FLAT facets. A real step has the two fitted
    planes offset everywhere: ``level_change`` when the offset is at least ``level_m`` (``SEAM_LEVEL_M``) at
    ``SEAM_LEVEL_SHARE`` of the stations; otherwise (a gently falling deck cut in flat pieces: the planes nearly meet at the
    seam) ``flat_seam``. The points are not used: sampled jumps beside a tall wall are too noisy to judge a step by. A
    non-finite station counts as "not offset"; a seam with no finite station is a flat seam with median 0."""
    d = seam_offsets(fa, fb, p0, p1)
    ok = np.isfinite(d)
    if not ok.any():
        return False, 0.0
    lim = (SEAM_LEVEL_M if level_m is None else level_m) - 1e-9
    return bool(((d >= lim) & ok).mean() >= SEAM_LEVEL_SHARE), float(np.median(d[ok]))


def measured_jump(fa: Facet, fb: Facet, p0: np.ndarray, p1: np.ndarray, q: np.ndarray | None, p: EngineParams) -> float:
    """Height jump (m) across p0-p1: measured from the points (``points_jump``); when a side has too few points to
    measure, the gap between the two planes at the middle of the line."""
    j = None
    if q is not None:
        d = p1 - p0
        n = np.array([-d[1], d[0]])
        a_left = float(np.dot(into(fa, p0, p1), n)) >= 0  # fa on the +normal side of p0 -> p1
        j = points_jump(q, p0, p1, fa.plane if a_left else fb.plane, fb.plane if a_left else fa.plane, p)
    if j is not None:
        return float(j)
    if q is not None and len(q):  # points exist but a side is too thin: the jump cannot be verified, so it is not called a level change
        return 0.0
    mid = (p0 + p1) / 2
    return abs(zat(fa.plane, *mid) - zat(fb.plane, *mid))


def into(f: Facet, p0: np.ndarray, p1: np.ndarray) -> np.ndarray:
    """Unit plan normal of the segment p0-p1 pointing into facet ``f`` (probed just beside the segment, so it is right
    for a concave facet whose far parts lie on both sides of the segment's line)."""
    d = p1 - p0
    n = np.array([-d[1], d[0]]) / max(float(np.hypot(*d)), 1e-12)
    mid = (p0 + p1) / 2
    for step in (0.05, 0.15, 0.4):
        if f.polygon.contains(shapely.Point(*(mid + step * n))):
            return n
        if f.polygon.contains(shapely.Point(*(mid - step * n))):
            return -n
    c = np.array(f.polygon.representative_point().coords[0])
    return n if float(np.dot(c - mid, n)) >= 0 else -n


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
