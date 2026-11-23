"""Flat-roof junk: small facets that are equipment, bulkheads or detail on a flat roof are part of the roof, not facets.

A facet under ``junk_area_m2`` whose shared boundary lies mostly (``junk_flat_share``) against flat facets is merged into
the flat neighbour it shares the longest boundary with. It does not matter whether the small facet is flat (a unit on a
platform: a level change smaller than a facet) or pitched (a pitched patch invented inside a flat roof). Small facets next
to pitched roofs (hip ends, dormers, a porch roof) are left to the other cleanup rules. Items are ``[label, Polygon]``.
Metres, building frame.
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .errors import Ctx
from .plane_math import pitch_rise


def _is_flat(plane, cut: float) -> bool:
    return pitch_rise(plane) < cut


def _merged(a: Polygon, b: Polygon, tol: float = 0.003) -> Polygon | None:
    """The union of two touching facets as one valid Polygon (exterior only, 1 micrometre grid), or None."""
    u = unary_union([a.buffer(tol), b.buffer(tol)]).buffer(-tol)
    if u.geom_type != "Polygon":
        u = unary_union([shapely.set_precision(a, 1e-6), shapely.set_precision(b, 1e-6)])  # exact union when the rounded one splits
        if u.geom_type != "Polygon":
            return None
    g = shapely.set_precision(Polygon(u.exterior), 1e-6)
    return g if g.geom_type == "Polygon" and g.is_valid and not g.is_empty else None


def _shared(a: Polygon, b: Polygon) -> float:
    """Length of the common boundary of two facets (within 3 cm)."""
    s = a.boundary.intersection(b.buffer(0.03))
    return float(s.length) if not s.is_empty else 0.0


def absorb_flat_junk(items: list, planes: list, ctx: Ctx) -> tuple[list, int]:
    """Merge small facets that sit against flat facets into the flat neighbour sharing the most boundary."""
    p = ctx.p
    items = [list(x) for x in items]
    n = 0
    changed = True
    while changed:
        ctx.check()
        changed = False
        for i in sorted(range(len(items)), key=lambda k: items[k][1].area):
            pg = items[i][1]
            if pg.area >= p.junk_area_m2:
                break
            shares = [(_shared(pg, items[j][1]), j) for j in range(len(items)) if j != i]
            shares = [(s, j) for s, j in shares if s > 0.05]
            tot = sum(s for s, _ in shares)
            if tot <= 0:
                continue
            flat = [(s, j) for s, j in shares if _is_flat(planes[items[j][0]], p.flat_cut_rise)]
            if sum(s for s, _ in flat) < p.junk_flat_share * tot:
                continue
            j = max(flat)[1]
            u = _merged(items[j][1], pg)
            if u is None:
                continue
            items[j][1] = u
            del items[i]
            n += 1
            changed = True
            break
    return items, n


def _width(pg: Polygon) -> float:
    return 2 * pg.area / max(pg.length, 1e-6)


def absorb_edge_strips(items: list, planes: list, outline: Polygon, ctx: Ctx) -> tuple[list, int]:
    """Merge long thin FLAT strips lying along the roof edge (gutter, fascia, an eave flattened by the overhang) into the
    neighbour they share the most boundary with: a flat facet narrower than ``strip_width_m`` (twice area over
    perimeter), under ``strip_area_m2``, with at least ``strip_outline_share`` of its boundary on the roof outline.
    Pitched thin facets are left alone (the small hip ends of a cut-up roof are real)."""
    p = ctx.p
    items = [list(x) for x in items]
    ob = outline.exterior
    n = 0
    changed = True
    while changed and len(items) > 1:
        ctx.check()
        changed = False
        for i in sorted(range(len(items)), key=lambda k: items[k][1].area):
            pg = items[i][1]
            if pg.area >= p.strip_area_m2:
                break
            if _width(pg) >= p.strip_width_m or not _is_flat(planes[items[i][0]], p.flat_cut_rise):
                continue
            on = pg.boundary.intersection(ob.buffer(0.05))
            if (0.0 if on.is_empty else on.length) < p.strip_outline_share * pg.length:
                continue
            shares = [(_shared(pg, items[j][1]), j) for j in range(len(items)) if j != i]
            s, j = max(shares)
            if s < 0.5:
                continue
            u = _merged(items[j][1], pg)
            if u is None:
                continue
            items[j][1] = u
            del items[i]
            n += 1
            changed = True
            break
    return items, n



def _outline_share(pg: Polygon, outline: Polygon, tol: float) -> float:
    on = pg.boundary.intersection(outline.exterior.buffer(tol))
    return 0.0 if on.is_empty else float(on.length) / max(pg.length, 1e-6)


def _split_strip(strip: Polygon, nbrs: list, planes: list, p) -> list[tuple[int, Polygon]]:
    """Cut a flat strip between its pitched neighbours along the plane-plane (ridge) line: every 0.1 m cell goes to the
    neighbour whose plane is LOWEST there (at a ridge the roof is the lower envelope of the two planes, each extended past the ridge). Returns
    [(item index, piece)]."""
    h = p.ridge_strip_cell_m
    minx, miny, maxx, maxy = strip.bounds
    xs = np.arange(minx + h / 2, maxx, h)
    ys = np.arange(miny + h / 2, maxy, h)
    gx, gy = np.meshgrid(xs, ys)
    inside = shapely.contains_xy(strip, gx, gy)
    z = np.stack([planes[lab][0] * gx + planes[lab][1] * gy + planes[lab][2] for _, lab in nbrs])
    owner = z.argmin(0)
    pieces = []
    for k, (idx, _) in enumerate(nbrs):
        sel = inside & (owner == k)
        if sel.any():
            cells = shapely.box(gx[sel] - h / 2, gy[sel] - h / 2, gx[sel] + h / 2, gy[sel] + h / 2)
            piece = unary_union(shapely.buffer(cells, 1e-4).tolist()).buffer(-1e-4).intersection(strip)
            pieces.append((idx, piece))
    return pieces


def absorb_enclosed_flat(items: list, planes: list, outline: Polygon, ctx: Ctx) -> tuple[list, int]:
    """Flat junk inside a pitched roof. (1) A thin flat strip between pitched facets that fall away from it is a rounded
    ridge (LiDAR rounds the ridge line): split between the neighbours along their plane intersection. (2) A small flat
    patch (under ``enclosed_flat_m2``) whose boundary is mostly against pitched facets and that has no edge of its own on
    the roof outline is a hole or sliver: merge into the pitched neighbour with the longest shared boundary. A real small
    flat roof (a porch) reaches the outline and stays."""
    p = ctx.p
    items = [list(x) for x in items]
    n = 0
    changed = True
    while changed:
        ctx.check()
        changed = False
        for i in sorted(range(len(items)), key=lambda k: items[k][1].area):
            lab, pg = items[i]
            if not _is_flat(planes[lab], p.flat_cut_rise) or pg.area >= max(p.ridge_strip_area_m2, p.enclosed_flat_m2):
                continue
            nb = [(_shared(pg, items[j][1]), j) for j in range(len(items)) if j != i]
            nb = [(s, j) for s, j in nb if s > 0.05]
            if _width(pg) < p.ridge_strip_width_m and pitch_rise(planes[lab]) < p.ridge_strip_max_rise:  # touching thin flat strips (rounded ridges of a cross gable) are one strip
                twin = [j for s, j in nb if s > 0.3 and pitch_rise(planes[items[j][0]]) < p.ridge_strip_max_rise
                        and _width(items[j][1]) < p.ridge_strip_width_m]
                u = _merged(items[twin[0]][1], pg) if twin else None
                if u is not None:
                    items[twin[0]][1] = u
                    del items[i]
                    changed = True
                    break
            tot = sum(s for s, _ in nb)
            pitched = [(s, j) for s, j in nb if not _is_flat(planes[items[j][0]], p.flat_cut_rise)]
            if tot <= 0 or sum(s for s, _ in pitched) < p.enclosed_pitched_share * tot:
                continue
            out_share = _outline_share(pg, outline, 0.05)
            c = pg.representative_point()
            zs = planes[lab][0] * c.x + planes[lab][1] * c.y + planes[lab][2]
            strip = (_width(pg) < p.ridge_strip_width_m and pg.area < p.ridge_strip_area_m2 and len(pitched) >= 2
                     and pitch_rise(planes[lab]) < p.ridge_strip_max_rise
                     and out_share < p.enclosed_outline_share
                     and max(planes[items[j][0]][0] * c.x + planes[items[j][0]][1] * c.y + planes[items[j][0]][2]
                             for _, j in pitched) >= zs + p.ridge_strip_rise_m)
            if strip:
                nbrs = [(j, items[j][0]) for _, j in sorted(pitched, reverse=True)[:6]]
                pieces = [(j, part) for j, piece in _split_strip(pg, nbrs, planes, p)
                          for part in (piece.geoms if hasattr(piece, "geoms") else [piece])
                          if part.geom_type == "Polygon" and part.area > 1e-4]
                trial = {j: items[j][1] for j, _ in nbrs}
                ok = bool(pieces)
                for j, part in pieces:
                    # the part joins its owner when it touches it, else the nearest of the strip's neighbours
                    order = sorted(trial, key=lambda k: (k != j, trial[k].distance(part)))
                    done = False
                    for k in order[:3]:
                        if trial[k].distance(part) > p.ridge_strip_join_m:
                            continue
                        u = _merged(trial[k], part, p.ridge_strip_join_m)
                        if u is not None:
                            trial[k], done = u, True
                            break
                    if not done:
                        ok = False
                        break
                if ok:
                    for j, poly in trial.items():
                        items[j][1] = poly
                    del items[i]
                    n += 1
                    changed = True
                    break
            elif pg.area < p.enclosed_flat_m2 and out_share < p.enclosed_outline_share:
                j = max(pitched)[1]
                u = _merged(items[j][1], pg)
                if u is not None:
                    items[j][1] = u
                    del items[i]
                    n += 1
                    changed = True
                    break
    return items, n


def _flat_fit_share(plane, pts: np.ndarray, tol: float) -> float:
    return float((np.abs(pts[:, 2] - (plane[0] * pts[:, 0] + plane[1] * pts[:, 1] + plane[2])) <= tol).mean()) if len(pts) else 1.0


def merge_flat_fitting(items: list, planes: list, q: np.ndarray, ctx: Ctx) -> tuple[list, int]:
    """One flat region is one facet, but only when one plane really fits it: adjacent flat facets (both under the flat cut,
    sharing at least ``flat_merge_min_edge_m`` of boundary, planes within ``level_change_m`` at the boundary) merge when a
    plane fitted to their union points keeps at least the share of points within ``fit_tol_m`` that the two facets had
    (less ``flat_merge_fit_drop``). A tilted drainage membrane (0.9/12 beside 0.0/12) is NOT merged: one plane would drop
    fit_all by 0.1-0.3 and push houses into poor_fit (tried and reverted without this test)."""
    from .plane_math import fit_plane

    p = ctx.p
    items = [list(x) for x in items]
    n = 0
    changed = True
    while changed:
        ctx.check()
        changed = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if not (_is_flat(planes[a[0]], p.flat_cut_rise) and _is_flat(planes[b[0]], p.flat_cut_rise)):
                    continue
                if _shared(a[1], b[1]) < p.flat_merge_min_edge_m or _boundary_gap(a[1], b[1], planes[a[0]], planes[b[0]]) >= p.level_change_m:
                    continue
                pa = q[shapely.contains_xy(a[1], q[:, 0], q[:, 1])]
                pb = q[shapely.contains_xy(b[1], q[:, 0], q[:, 1])]
                if len(pa) + len(pb) < p.flat_merge_min_pts:
                    continue
                pu = np.vstack([pa, pb])
                plane = fit_plane(pu)
                own = (_flat_fit_share(planes[a[0]], pa, p.fit_tol_m) * len(pa) + _flat_fit_share(planes[b[0]], pb, p.fit_tol_m) * len(pb)) / len(pu)
                if _flat_fit_share(plane, pu, p.fit_tol_m) < own - p.flat_merge_fit_drop or float(np.hypot(plane[0], plane[1])) * 12 >= p.flat_cut_rise:
                    continue
                u = _merged(a[1], b[1])
                if u is None:
                    continue
                planes.append(np.array(plane, float))
                items[i] = [len(planes) - 1, u]
                del items[j]
                n += 1
                changed = True
                break
            if changed:
                break
    return items, n


def _boundary_gap(a: Polygon, b: Polygon, pa, pb) -> float:
    """Largest height difference between planes pa and pb over the common boundary of a and b (sampled)."""
    sh = a.boundary.intersection(b.buffer(0.03))
    if sh.is_empty:
        return 1e9
    gap = 0.0
    for f in (0.1, 0.3, 0.5, 0.7, 0.9):
        pt = sh.interpolate(f, normalized=True)
        gap = max(gap, abs(pa[0] * pt.x + pa[1] * pt.y + pa[2] - (pb[0] * pt.x + pb[1] * pt.y + pb[2])))
    return gap
