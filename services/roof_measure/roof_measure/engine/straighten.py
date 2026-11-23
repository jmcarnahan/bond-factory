"""Straighten the facet partition: node the linework, simplify every junction-to-junction chain once (both
neighbours share it), snap close junctions, then re-polygonize. Cannot overlap and cannot leave gaps. Metres."""

from __future__ import annotations

import math

import numpy as np
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import linemerge, polygonize, unary_union

from .errors import Ctx
from .params import EngineParams
from .plane_math import pdist
from .vectorise import project_to_crease


def _rot(pts: np.ndarray, th: float, inv: bool = False) -> np.ndarray:
    a = math.radians(-th if not inv else th)
    mat = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    return pts @ mat.T


def _dp(pts: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker simplification of a polyline (ends kept)."""
    if len(pts) <= 2:
        return pts
    out = np.array(LineString(pts).simplify(tol, preserve_topology=False).coords)
    return out if len(out) >= 2 else pts


def _drop_short_collinear(pts, min_seg: float, col_deg: float) -> np.ndarray:
    """Remove near-collinear interior vertices, then the interior end of the shortest segment under ``min_seg``."""
    pts = [np.array(q) for q in pts]
    for _ in range(40):
        if len(pts) <= 2:
            break
        done = True
        for i in range(1, len(pts) - 1):
            a, b = pts[i] - pts[i - 1], pts[i + 1] - pts[i]
            la, lb = np.hypot(*a), np.hypot(*b)
            if la < 1e-9 or lb < 1e-9:
                del pts[i]
                done = False
                break
            if np.dot(a, b) / (la * lb) > math.cos(math.radians(col_deg)):
                del pts[i]
                done = False
                break
        if not done:
            continue
        segs = [(np.hypot(*(pts[i + 1] - pts[i])), i) for i in range(len(pts) - 1)]
        short = [s for s in segs if s[0] < min_seg]
        if not short:
            break
        _, i = min(short)
        if i + 1 < len(pts) - 1:
            del pts[i + 1]
        elif i > 0:
            del pts[i]
        else:
            break
    return np.array(pts)


def _axis_snap(pts: np.ndarray, theta: float, tol_deg: float) -> np.ndarray:
    """Staircase snap of the interior vertices of a polyline to the building axes (ends fixed)."""
    if len(pts) < 3:
        return pts
    w = _rot(np.array(pts), theta)
    m = len(w) - 1
    tan = math.tan(math.radians(tol_deg))
    for i in range(m - 1):
        d = w[i + 1] - w[i]
        if abs(d[1]) <= tan * abs(d[0]):
            w[i + 1, 1] = w[i, 1]
        elif abs(d[0]) <= tan * abs(d[1]):
            w[i + 1, 0] = w[i, 0]
    d = w[m] - w[m - 1]
    if m >= 2:
        if abs(d[1]) <= tan * abs(d[0]):
            w[m - 1, 1] = w[m, 1]
        elif abs(d[0]) <= tan * abs(d[1]):
            w[m - 1, 0] = w[m, 0]
    return _rot(w, theta, inv=True)


def _simplify_chain(pts: np.ndarray, labs: tuple, planes: list, theta: float, p: EngineParams) -> np.ndarray:
    """Simplify one chain with fixed ends. ``labs`` are the facet labels either side (None = outside)."""
    if len(pts) <= 2:
        return pts
    col = p.chain_collinear_deg
    if labs[0] is None or labs[1] is None:
        return _drop_short_collinear(_dp(pts, p.chain_free_tol_m), p.chain_free_min_seg_m, col)
    pa, pb = planes[labs[0]], planes[labs[1]]
    gd = np.hypot(pa[0] - pb[0], pa[1] - pb[1])
    crease = False
    if gd > p.chain_crease_gdiff:
        dz = np.abs((pa[0] - pb[0]) * pts[:, 0] + (pa[1] - pb[1]) * pts[:, 1] + (pa[2] - pb[2]))
        crease = bool((dz / gd).max() < p.chain_crease_gap_m)  # every vertex close to the intersection line
    if crease:
        return _drop_short_collinear(_dp(pts, p.chain_crease_tol_m), p.chain_crease_min_seg_m, col)
    ls0 = LineString([pts[0], pts[-1]])
    if ls0.length > 1e-6:
        dev = max(ls0.distance(Point(q)) for q in pts)
        if dev <= max(p.chain_straight_m, p.chain_straight_share * ls0.length):
            return np.array([pts[0], pts[-1]])  # one straight segment end to end
    d = _axis_snap(_dp(pts, p.chain_axis_tol_m), theta, p.chain_axis_snap_deg)
    return _drop_short_collinear(d, p.chain_min_seg_m, col)


def _on_crease(pt: np.ndarray, labs: tuple, planes: list, p: EngineParams) -> bool:
    """True when ``pt`` lies on the intersection line of the two different planes beside a chain."""
    if labs[0] is None or labs[1] is None:
        return False
    pa, pb = planes[labs[0]], planes[labs[1]]
    gd = np.hypot(pa[0] - pb[0], pa[1] - pb[1])
    return bool(gd > p.chain_crease_gdiff
                and abs((pa[0] - pb[0]) * pt[0] + (pa[1] - pb[1]) * pt[1] + (pa[2] - pb[2])) / gd < p.chain_crease_gap_m)


def _extend_to_outline(s: np.ndarray, labs: tuple, planes: list, outline: Polygon, p: EngineParams) -> np.ndarray:
    """A chain whose last segment lies on a plane-plane crease and ends on the outline is carried along the crease line
    to the outline: the raster node sits a cell or two off the corner (a hip ending 0.6 m short of the eave corner)."""
    s = s.copy()
    ob = outline.exterior
    pa, pb = planes[labs[0]], planes[labs[1]]
    line_dir = np.array([-(pa[1] - pb[1]), pa[0] - pb[0]])
    line_dir = line_dir / max(float(np.hypot(*line_dir)), 1e-9)
    for end, prev in ((len(s) - 1, len(s) - 2), (0, 1)):
        if ob.distance(Point(*s[end])) >= p.outline_touch_m or not _on_crease(s[prev], labs, planes, p):
            continue
        d = line_dir if float(np.dot(line_dir, s[end] - s[prev])) >= 0 else -line_dir
        base = project_to_crease(s[prev], pa, pb)
        if base is None or float(np.dot(s[end] - base, d)) < 0:
            continue
        ray = LineString([base, base + d * (float(np.hypot(*(s[end] - base))) + p.crease_extend_m)])
        hit = ray.intersection(ob)
        pts = [np.array(g.coords[0]) for g in (hit.geoms if hasattr(hit, "geoms") else [hit]) if g.geom_type == "Point"]
        pts = [q for q in pts if float(np.hypot(*(q - s[end]))) <= p.crease_extend_m]
        if pts:
            s[end] = min(pts, key=lambda q: float(np.hypot(*(q - s[end]))))
    return s


def _chains(items: list, outline: Polygon, tree, polys: list, p: EngineParams) -> list:
    """Junction-to-junction chains of the partition linework with the facet labels on their two sides."""
    lines = shapely.union_all([q.exterior for q in polys] + [outline.exterior], grid_size=1e-3)
    merged = linemerge(lines)
    chains = list(merged.geoms) if hasattr(merged, "geoms") else [merged]

    def owner(x: float, y: float):
        for i in sorted(int(t) for t in tree.query(Point(x, y))):
            if polys[i].contains(Point(x, y)):
                return items[i][0]
        return None

    off = p.owner_offset_m
    info = []
    for ch in chains:
        c = np.array(ch.coords)
        if len(c) < 2:
            continue
        mid = ch.interpolate(0.5, normalized=True)
        s0 = ch.project(mid)
        p1, p2 = ch.interpolate(max(s0 - 0.2, 0)), ch.interpolate(min(s0 + 0.2, ch.length))
        d = np.array([p2.x - p1.x, p2.y - p1.y])
        nd = np.hypot(*d)
        if nd < 1e-9:
            labs = (None, None)
        else:
            n = np.array([-d[1], d[0]]) / nd
            labs = (owner(mid.x + off * n[0], mid.y + off * n[1]), owner(mid.x - off * n[0], mid.y - off * n[1]))
        info.append([c, labs])
    return info


def _snap_junctions(info: list, outline: Polygon, p: EngineParams) -> dict[int, np.ndarray]:
    """New position per chain end (index 2k = start, 2k+1 = end of chain k): close ends become one node,
    preferring a point on the outline."""
    ends = []
    for c, _ in info:
        ends.extend([c[0], c[-1]])
    ev = np.array(ends)
    ob = outline.boundary
    on_o = np.array([ob.distance(Point(*e)) < p.outline_touch_m for e in ev])
    par = list(range(len(ev)))

    def find(a: int) -> int:
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    has_o = {i: bool(on_o[i]) for i in range(len(ev))}
    pairs = cKDTree(ev).query_pairs(p.node_tol_m)
    # The merge rule (two outline ends never join) makes the result depend on pair order. The reference walked the
    # set in CPython's hash order; a fixed order keeps runs identical: highest (i, j) first reproduces the reference
    # on 159 of 160 tuning houses byte for byte (the other one within IoU 0.98). Never iterate the set itself.
    for i, j in sorted(pairs, reverse=True):
        a, b = find(i), find(j)
        if a == b or (has_o[a] and has_o[b]):
            continue
        par[a] = b
        has_o[b] = has_o[a] or has_o[b]
    groups: dict[int, list[int]] = {}
    for i in range(len(ev)):
        groups.setdefault(find(i), []).append(i)
    newpos = {}
    for idx in groups.values():
        if len(idx) == 1:
            continue
        oi = [i for i in idx if on_o[i]]
        tgt = ev[oi[0]] if oi else ev[idx].mean(0)
        for i in idx:
            newpos[i] = tgt
    return newpos


def _cells_to_facets(cells: list, outline: Polygon, items: list, polys: list, tree, planes: list | None = None,
                     q: np.ndarray | None = None, p: EngineParams | None = None) -> list:
    """Give each polygonized cell to the original facet covering most of it (a small cell to the facet whose plane fits
    its points best, unless that would wrap one facet round another); union per facet."""
    rec = []  # (cell, default facet, chosen facet)
    for cl in cells:
        ci = cl.intersection(outline)
        if ci.is_empty or ci.area < 1e-5 or ci.area < 0.5 * cl.area:
            continue
        default, ba = None, 0.0
        for i in sorted(int(t) for t in tree.query(cl)):
            a = cl.intersection(polys[i]).area
            if a > ba:
                ba, default = a, i
        best = default
        if p is not None and q is not None and planes is not None and ci.area < p.small_cell_m2:
            best = _best_fit_facet(ci, default, items, polys, tree, planes, q, p)
        if default is None:
            default = best = int(tree.nearest(cl.representative_point()))
        rec.append((ci, default, best))
    groups = _group(rec, set())
    wrapped = {i for i, cs in groups.items() if _has_hole(cs)}
    if wrapped:
        groups = _group(rec, wrapped)
    out = []
    for i, cs in groups.items():
        u = unary_union(cs)
        for part in (list(u.geoms) if hasattr(u, "geoms") else [u]):
            if part.geom_type == "Polygon" and part.area > 0.02:
                out.append([items[i][0], shapely.set_precision(Polygon(part.exterior), 1e-6)])
    return out


def _group(rec: list, revert: set) -> dict:
    """Cells per facet; a cell whose chosen or default facet is in ``revert`` goes back to its default facet."""
    groups: dict[int, list] = {}
    for ci, default, best in rec:
        groups.setdefault(default if (best in revert or default in revert) else best, []).append(ci)
    return groups


def _has_hole(cs: list) -> bool:
    u = unary_union(cs)
    return any(len(g.interiors) for g in (u.geoms if hasattr(u, "geoms") else [u]) if g.geom_type == "Polygon")


def _best_fit_facet(cell: Polygon, default: int | None, items: list, polys: list, tree, planes: list, q: np.ndarray,
                    p: EngineParams) -> int | None:
    """A small cell goes to the touching facet whose PLANE fits the points inside it best, not to the facet it was
    cut from: the cell is a corner the straightened crease moved to the other side. Needs ``small_cell_min_pts``."""
    m = shapely.contains_xy(cell.buffer(p.small_cell_reach_m), q[:, 0], q[:, 1])
    if int(m.sum()) < p.small_cell_min_pts:
        return default
    pts = q[m]
    cand = {int(t) for t in tree.query(cell.buffer(0.05))}
    if default is not None:
        cand.add(default)
    best, bs = default, None
    for i in sorted(cand):
        sc = float(np.median(np.abs(pdist(planes[items[i][0]], pts))))
        if bs is None or sc < bs - 1e-9:
            best, bs = i, sc
    return best


def straighten_partition(items: list, outline: Polygon, planes: list, theta: float, ctx: Ctx,
                         q: np.ndarray | None = None) -> list:
    """Straighten the shared linework of ``items`` (``[label, Polygon]``) inside ``outline``; returns new items."""
    p = ctx.p
    polys = [q for _, q in items]
    tree = shapely.STRtree(polys)
    info = _chains(items, outline, tree, polys, p)
    ctx.check()
    newpos = _snap_junctions(info, outline, p)
    new_lines = []
    for k, (c, labs) in enumerate(info):
        c = c.copy()
        if 2 * k in newpos:
            c[0] = newpos[2 * k]
        if 2 * k + 1 in newpos:
            c[-1] = newpos[2 * k + 1]
        s = _dp(c, p.chain_closed_tol_m) if np.allclose(c[0], c[-1]) else _simplify_chain(c, labs, planes, theta, p)
        if len(s) >= 2 and labs[0] is not None and labs[1] is not None:
            s = _extend_to_outline(s, labs, planes, outline, p)
        if len(s) >= 2:
            new_lines.append(LineString(s))
    net = shapely.union_all(new_lines + [outline.exterior], grid_size=1e-3) if new_lines else outline.exterior
    return _cells_to_facets(list(polygonize(net)), outline, items, polys, tree, planes, q, p)
