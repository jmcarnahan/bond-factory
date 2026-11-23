"""Facet statistics: plane per polygon, independent pitch fit, areas, supported share. Metres in, square feet out."""

from __future__ import annotations

import math

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Polygon

from .params import EngineParams
from .plane_math import PlaneLike, aspect_deg, pres
from .types import Facet

SQM2SQFT = 10.7639  # square feet per square metre (the reference's constant, kept for parity)


def pitch_fit(poly: Polygon, q: np.ndarray, plane: PlaneLike, p: EngineParams) -> tuple[float | None, float | None, int]:
    """Independent plane fit to the points inside ``poly``: (rise, sigma of the rise, n). None when under 8 points."""
    m = shapely.contains_xy(poly, q[:, 0], q[:, 1])
    pts = q[m]
    if len(pts) < 8:
        return None, None, len(pts)
    pts = pts[np.abs(pres(plane, pts)) < p.pitch_fit_tol_m]
    if len(pts) < 8:
        return None, None, len(pts)
    a = np.c_[pts[:, 0], pts[:, 1], np.ones(len(pts))]
    sol, *_ = np.linalg.lstsq(a, pts[:, 2], rcond=None)
    res = pts[:, 2] - a @ sol
    s2 = res.var(ddof=3)
    try:
        cov = s2 * np.linalg.inv(a.T @ a)
    except np.linalg.LinAlgError:
        return None, None, len(pts)
    g = np.array(sol[:2])
    gn = np.linalg.norm(g)
    if gn < 1e-9:
        sg = math.sqrt(max(cov[0, 0], cov[1, 1]))
    else:
        u = g / gn
        sg = math.sqrt(max(u @ cov[:2, :2] @ u, 0))
    return 12.0 * gn, 12.0 * sg, len(pts)


def supported_pct(poly: Polygon, tree: cKDTree, p: EngineParams) -> float | None:
    """Percent of a 0.25 m sample grid inside ``poly`` that has a roof point within 0.5 m."""
    step = p.supported_step_m
    minx, miny, maxx, maxy = poly.bounds
    xs = np.arange(minx + step / 2, maxx, step)
    ys = np.arange(miny + step / 2, maxy, step)
    if len(xs) == 0 or len(ys) == 0:
        return None
    gx, gy = np.meshgrid(xs, ys)
    m = shapely.contains_xy(poly, gx, gy)
    if m.sum() == 0:
        return None
    d, _ = tree.query(np.c_[gx[m], gy[m]], k=1)
    return float((d <= p.supported_reach_m).mean() * 100)


def _trust_own_points(plane: np.ndarray, poly: Polygon, q: np.ndarray, p: EngineParams) -> np.ndarray:
    """When the facet's own points disagree about the 2/12 cut (and are tight), rescale its gradient to their pitch."""
    pf, ps, _ = pitch_fit(poly, q, plane, p)
    g = math.hypot(plane[0], plane[1])
    cut = p.flat_cut_rise
    if (pf is not None and ps is not None and ps < p.flip_sigma and pf >= 0.5 and g > 1e-6
            and ((12.0 * g < cut) != (pf < cut))):
        sc = (pf / 12.0) / g
        plane[0] *= sc
        plane[1] *= sc
        m = shapely.contains_xy(poly, q[:, 0], q[:, 1])
        if m.sum():
            plane[2] = float(np.median(q[m, 2] - plane[0] * q[m, 0] - plane[1] * q[m, 1]))
    return plane


def facet_stats(items: list, planes: list, q: np.ndarray, p: EngineParams) -> list[Facet]:
    """Facets (ids f1.. from north to south, then west to east) with plane, pitch, areas and fit statistics."""
    facets = []
    order = sorted(items, key=lambda t: (-t[1].centroid.y, t[1].centroid.x))
    for k, (label, poly) in enumerate(order):
        pl = _trust_own_points(np.array(planes[label], float), poly, q, p)
        g = math.hypot(pl[0], pl[1])
        rise = 12.0 * g
        cosv = 1.0 / math.sqrt(1 + g * g)
        plan = poly.area * SQM2SQFT
        inside = shapely.contains_xy(poly, q[:, 0], q[:, 1])
        r = pres(pl, q[inside]) if inside.sum() else np.array([0.0])
        pf, ps, _ = pitch_fit(poly, q, pl, p)
        facets.append(Facet(
            id=f"f{k + 1}", polygon=poly, plane=tuple(float(v) for v in pl), label=int(label), pitch_rise=float(rise),
            aspect_deg=float(aspect_deg(pl)) if g > 1e-3 else 0.0, roof_type="flat" if rise < p.flat_cut_rise else "pitched",
            plan_area_sqft=float(plan), area_sqft=float(plan / cosv), points=int(inside.sum()), rms_m=float(r.std()),
            pitch_fit=None if pf is None else round(float(pf), 2), pitch_sigma=None if ps is None else round(float(ps), 2)))
    return facets
