"""Label raster to facet polygons: trace each label, coverage-simplify, snap shared vertices onto plane creases."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import shapely
from shapely.geometry import Polygon

from .errors import Ctx
from .plane_math import PlaneLike, zat
from .raster import trace_polys


def _key(c) -> tuple[float, float]:
    return (round(float(c[0]), 6), round(float(c[1]), 6))


def plane_cross_point(pa: PlaneLike, pb: PlaneLike, pc: PlaneLike) -> np.ndarray | None:
    """Plan position where three planes meet (None when two are nearly parallel)."""
    a = np.array([[pa[0] - pb[0], pa[1] - pb[1]], [pa[0] - pc[0], pa[1] - pc[1]]])
    if abs(np.linalg.det(a)) < 0.02:
        return None
    return np.linalg.solve(a, np.array([pb[2] - pa[2], pc[2] - pa[2]]))


def project_to_crease(pt: Sequence[float], pa: PlaneLike, pb: PlaneLike) -> np.ndarray | None:
    """Nearest plan point to ``pt`` on the line where planes pa and pb have equal height (None when parallel)."""
    gx, gy, c = pa[0] - pb[0], pa[1] - pb[1], pa[2] - pb[2]
    n2 = gx * gx + gy * gy
    if n2 < 1e-4:
        return None
    t = (gx * pt[0] + gy * pt[1] + c) / n2
    return np.array([pt[0] - gx * t, pt[1] - gy * t])


def vectorise(lab: np.ndarray, origin: tuple[float, float, float], planes: list, ctx: Ctx) -> list:
    """Label raster to ``[(label, Polygon)]`` with coverage-simplified shared linework, creases snapped."""
    p = ctx.p
    minx, miny, h = origin
    polys, labels = [], []
    for label in range(len(planes)):
        ctx.check()
        m = lab == label
        if m.sum() == 0:
            continue
        ps = trace_polys(m, minx, miny, h)
        polys.append(shapely.union_all(ps) if len(ps) > 1 else ps[0])
        labels.append(label)
    outside = trace_polys(lab < 0, minx, miny, h)  # the outside is a coverage member too
    cov = shapely.coverage_simplify(np.array(polys + outside, dtype=object), p.simplify_tol_m, simplify_boundary=False)
    res = []
    for label, g in zip(labels, cov[:len(polys)], strict=True):
        for part in (list(g.geoms) if g.geom_type == "MultiPolygon" else [g]):
            if part.area > p.min_polygon_m2:
                res.append((label, part))
    outs = []
    for g in cov[len(polys):]:
        outs += list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
    return snap_creases(res, outs, planes, ctx)


def _register(vlab: dict, poly: Polygon, label: int) -> None:
    for r in [poly.exterior, *poly.interiors]:
        for c in r.coords:
            vlab.setdefault(_key(c), set()).add(label)


def _outline_neighbours(items: list) -> dict:
    nbrs: dict = {}
    for _, poly in items:
        for r in [poly.exterior, *poly.interiors]:
            cs = [_key(c) for c in r.coords][:-1]
            for i, k in enumerate(cs):
                nbrs.setdefault(k, set()).update([cs[i - 1], cs[(i + 1) % len(cs)]])
    return nbrs


def _snap_pair(k, labs, real, planes, vlab, nbrs, p) -> np.ndarray | None:
    """New position of a vertex shared by two facets (and maybe the outside): onto their crease line."""
    pt = np.array(k)
    pa, pb = planes[real[0]], planes[real[1]]
    if abs(zat(pa, *pt) - zat(pb, *pt)) > p.crease_gap_m:
        return None
    if np.linalg.norm(np.array(pa[:2]) - np.array(pb[:2])) < p.crease_parallel:
        return None
    q = pt
    if -1 in labs:  # junction with the outside: push outward along the chain direction, then project
        cand = sorted(kk for kk in nbrs.get(k, []) if len(vlab.get(kk, set()) - {-1}) == 2 and -1 not in vlab[kk])
        if cand:
            w = np.array(cand[0])
            u = pt - w
            nu = np.hypot(*u)
            if nu > 1e-6:
                q = pt + u / nu * 0.5
    x = project_to_crease(q, pa, pb)
    if x is not None and np.hypot(*(x - pt)) < p.crease_max_move_m + (0.5 if -1 in labs else 0):
        return x
    return None


def snap_creases(items: list, outs: list, planes: list, ctx: Ctx) -> list:
    """Move vertices shared by two facets onto their plane-intersection line, and three-facet junctions onto the
    point where the three planes meet (never more than ``crease_max_move_m`` and ``crease_junction_move_m``)."""
    p = ctx.p
    vlab: dict = {}
    for label, poly in items:
        _register(vlab, poly, label)
    for poly in outs:
        _register(vlab, poly, -1)
    nbrs = _outline_neighbours(items)
    newpos = {}
    for k, labs in vlab.items():
        real = sorted(x for x in labs if x >= 0)
        pt = np.array(k)
        if len(real) == 3:
            x = plane_cross_point(*(planes[i] for i in real))
            if x is not None and np.hypot(*(x - pt)) < p.crease_junction_move_m:
                newpos[k] = x
        elif len(real) == 2:
            x = _snap_pair(k, labs, real, planes, vlab, nbrs, p)
            if x is not None:
                newpos[k] = x
    out = []
    for label, poly in items:
        def mv(r):
            return [tuple(newpos.get(_key(c), c)) for c in r.coords]

        q = Polygon(mv(poly.exterior), [mv(h) for h in poly.interiors])
        if not q.is_valid:
            q = q.buffer(0)
            if q.geom_type == "MultiPolygon":
                q = max(q.geoms, key=lambda g: g.area)
        out.append((label, q))
    return out
