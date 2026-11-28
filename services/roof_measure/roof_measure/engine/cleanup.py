"""Facet cleanup on the vector partition: clip to the outline, absorb slivers, re-unite same-plane pieces,
merge small facets and coplanar neighbours. Items are ``[label, Polygon]`` lists. Metres, building frame."""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .errors import Ctx
from .params import EngineParams
from .plane_math import pres


def _exact(poly) -> Polygon:
    """Exterior only (islands absorbed), snapped to a 1 micrometre grid so neighbours share vertices. A MultiPolygon
    (two parts a few centimetres apart) gives its largest part, so this never raises."""
    if poly.geom_type != "Polygon":
        parts = [g for g in getattr(poly, "geoms", []) if g.geom_type == "Polygon"]
        if not parts:
            return Polygon()
        poly = max(parts, key=lambda g: g.area)
    g = shapely.set_precision(Polygon(poly.exterior), 1e-6)
    if g.geom_type != "Polygon":
        parts = [x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon"]
        g = max(parts, key=lambda x: x.area) if parts else Polygon()
    return g


def _clip(items: list, outline: Polygon) -> list:
    out = []
    for label, poly in items:
        q = poly.intersection(outline)
        for r in (list(q.geoms) if hasattr(q, "geoms") else [q]):
            if r.geom_type == "Polygon" and r.area > 0.02:
                out.append([label, _exact(r)])
    return out


def _absorb_slivers(out: list, p: EngineParams, ctx: Ctx) -> None:
    """Merge every sliver (tiny, or small and thin) into the neighbour it shares most boundary with."""
    changed = True
    while changed:
        ctx.check()
        changed = False
        out.sort(key=lambda t: t[1].area)
        for i, (_, poly) in enumerate(out):
            width = 2 * poly.area / max(poly.length, 1e-6)
            if not ((poly.area < p.sliver_area_m2 or (poly.area < p.sliver_thin_area_m2 and width < p.sliver_width_m))
                    and len(out) > 1):
                continue
            best, bl = None, 0.0
            for j, (_, p2) in enumerate(out):
                if j == i:
                    continue
                s = poly.buffer(0.03).intersection(p2.boundary).length if poly.buffer(0.03).intersects(p2) else 0.0
                if s > bl:
                    bl, best = s, j
            if best is not None and bl > 0.05:
                u = unary_union([out[best][1], poly])
                u = u if u.geom_type == "Polygon" else u.buffer(0.01)
                if u.geom_type != "Polygon":
                    continue  # two parts too far apart to join: this sliver stays
                out[best][1] = _exact(u)
                del out[i]
                changed = True
                break


def _reunite_same_label(out: list, ctx: Ctx) -> None:
    changed = True
    while changed:
        ctx.check()
        changed = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if out[i][0] == out[j][0] and out[i][1].buffer(0.03).intersects(out[j][1]):
                    u = unary_union([out[i][1].buffer(0.005), out[j][1].buffer(0.005)]).buffer(-0.005)
                    if u.geom_type == "Polygon":
                        out[i][1] = _exact(u)
                        del out[j]
                        changed = True
                        break
            if changed:
                break


def valid_polygon(poly: Polygon) -> Polygon:
    """``poly`` when valid; else its zero-area pinch (a ring touching itself) removed by ``buffer(0)``, keeping the largest
    part. The area is unchanged to the last digit: the pinch has none."""
    if poly.is_valid:
        return poly
    g = poly.buffer(0)
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda x: x.area)
    return g if g.geom_type == "Polygon" and not g.is_empty else poly


def repair_items(items: list) -> list:
    """Every facet polygon of ``items`` valid (see ``valid_polygon``)."""
    return [[label, valid_polygon(poly)] for label, poly in items]


def clean_facets(items: list, outline: Polygon, ctx: Ctx) -> list:
    """Clip to the outline, merge slivers, re-unite touching pieces of one plane."""
    out = _clip(items, outline)
    _absorb_slivers(out, ctx.p, ctx)
    _reunite_same_label(out, ctx)
    return out


def _crease_share(i: int, items: list, planes: list, p: EngineParams) -> float:
    """Share of facet i's shared boundary that lies on the plane-plane intersection line (planes not parallel)."""
    li, pg = items[i]
    tot = on = 0.0
    for j, (l2, p2) in enumerate(items):
        if j == i:
            continue
        sh = pg.boundary.intersection(p2.buffer(0.05))
        if sh.is_empty or sh.length < 0.3:
            continue
        tot += sh.length
        a, b = planes[li], planes[l2]
        if np.hypot(a[0] - b[0], a[1] - b[1]) < p.crease_parallel:
            continue
        pts = [sh.interpolate(f, normalized=True) for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
        gap = max(abs(a[0] * q.x + a[1] * q.y + a[2] - (b[0] * q.x + b[1] * q.y + b[2])) for q in pts)
        if gap < p.s4_crease_gap:
            on += sh.length
    return on / tot if tot > 0 else 0.0


def _keeps_small(i: int, items: list, planes: list, q: np.ndarray, inside: np.ndarray, p: EngineParams) -> bool:
    """Step 4: a well-fitted small facet meeting its neighbours along crease lines is a hip end or dormer: keep."""
    label, pg = items[i]
    return bool(p.s4_gentle and pg.area >= p.s4_keep_area and inside.sum() >= p.s4_pts
                and pres(planes[label], q[inside]).std() < p.s4_rms
                and _crease_share(i, items, planes, p) >= p.s4_crease_share)


def _best_neighbour(i: int, items: list, planes: list, q: np.ndarray, inside: np.ndarray, p: EngineParams):
    """The neighbour whose rms rises least (and below ``small_merge_rms_m``) when it absorbs facet i's points."""
    label, pg = items[i]
    best = None
    for j, (l2, p2) in enumerate(items):
        if j == i:
            continue
        shared = pg.buffer(0.05).intersection(p2.boundary).length
        if shared < 0.5:
            continue
        mj = shapely.contains_xy(p2, q[:, 0], q[:, 1])
        rj = pres(planes[l2], q[mj]) if mj.sum() else np.zeros(1)
        ri = pres(planes[l2], q[inside]) if inside.sum() else np.zeros(0)
        rms0 = float(np.sqrt((rj ** 2).mean()))
        rms1 = float(np.sqrt((np.concatenate([rj, ri]) ** 2).mean()))
        if l2 == label or rms1 - rms0 < p.small_merge_rms_m:
            sc = (rms1 - rms0, -shared)
            if best is None or sc < best[0]:
                best = (sc, j)
    return best


def _longest_neighbour(i: int, items: list):
    """(score, index) of the neighbour sharing the most boundary with facet i (at least 0.5 m), else None."""
    pg = items[i][1]
    shared = [(pg.buffer(0.05).intersection(p2.boundary).length, j) for j, (_, p2) in enumerate(items) if j != i]
    shared = [t for t in shared if t[0] >= 0.5]
    return None if not shared else (None, max(shared)[1])


def merge_small_facets(items: list, planes: list, q: np.ndarray, ctx: Ctx) -> tuple[list, int]:
    """A facet under ``small_facet_m2`` merges into the neighbour whose residual rms rises least."""
    p = ctx.p
    items = [list(x) for x in items]
    merged = 0
    while True:
        ctx.check()
        done = True
        for i in sorted(range(len(items)), key=lambda k: items[k][1].area):
            pg = items[i][1]
            if pg.area >= p.small_facet_m2:
                break
            inside = shapely.contains_xy(pg, q[:, 0], q[:, 1])
            if _keeps_small(i, items, planes, q, inside, p):
                continue
            best = _best_neighbour(i, items, planes, q, inside, p)
            if best is None and inside.sum() < p.plane_min_pts:  # too few returns to be a plane of its own: the longest shared boundary takes it
                best = _longest_neighbour(i, items)
            if best is not None:
                j = best[1]
                u = unary_union([items[j][1].buffer(0.003), pg.buffer(0.003)]).buffer(-0.003)
                if u.geom_type == "Polygon":
                    items[j][1] = _exact(u)
                    del items[i]
                    merged += 1
                    done = False
                    break
        if done:
            break
    return items, merged


def merge_coplanar_facets(items: list, planes: list, ctx: Ctx) -> tuple[list, int]:
    """Adjacent facets of (nearly) the same plane, or of the same flat membrane, are one facet."""
    p = ctx.p
    items = [list(x) for x in items]
    n = 0
    while True:
        ctx.check()
        hit = _find_coplanar_pair(items, planes, p)
        if hit is None:
            break
        i, j = hit
        keep, drop = (i, j) if items[i][1].area >= items[j][1].area else (j, i)
        u = unary_union([items[keep][1].buffer(0.003), items[drop][1].buffer(0.003)]).buffer(-0.003)
        if u.geom_type != "Polygon":
            break
        items[keep][1] = _exact(u)
        del items[drop]
        n += 1
    return items, n


def _find_coplanar_pair(items: list, planes: list, p: EngineParams) -> tuple[int, int] | None:
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            li, pi = items[i]
            lj, pj = items[j]
            if li == lj:
                continue
            sh = pi.boundary.intersection(pj.buffer(0.03))
            if sh.length < 0.5:
                continue
            a, b = planes[li], planes[lj]
            gd = np.hypot(a[0] - b[0], a[1] - b[1])
            if sh.geom_type not in ("LineString", "MultiLineString"):
                continue
            pts = [sh.interpolate(f, normalized=True) for f in (0.15, 0.5, 0.85)]
            gap = np.mean([abs(a[0] * q.x + a[1] * q.y + a[2] - (b[0] * q.x + b[1] * q.y + b[2])) for q in pts])
            if gd < p.coplanar_facet_gtol and gap < p.coplanar_facet_gap_m:
                return i, j
    return None


def close_gaps(items: list, outline: Polygon, p: EngineParams) -> tuple[list, int]:
    """Thin channels between facets inside the outline (narrower than ``gap_close_width_m``: twice area over perimeter)
    are given to the facet that shares the most boundary with them, so the facets tile the roof. A real hole (wider)
    stays. A gap with holes of its own is a frame round facets, not a channel between them: it stays (a hairline frame
    round the whole roof, given to one facet, swallowed every other facet). No merge may cover another facet by more
    than ``gap_close_min_m2``. Returns (items, number of gaps closed)."""
    if not items:
        return items, 0
    items = [list(x) for x in items]
    union = unary_union([g for _, g in items])
    gap = outline.difference(union)
    n = 0
    for g in (gap.geoms if hasattr(gap, "geoms") else [gap]):
        if g.geom_type != "Polygon" or list(g.interiors) or g.area < p.gap_close_min_m2 \
                or 2 * g.area / max(g.length, 1e-6) >= p.gap_close_width_m:
            continue
        shares = [(g.buffer(0.2).intersection(items[j][1].boundary).length, j) for j in range(len(items))]
        shares = [(s, j) for s, j in shares if s > 0]
        if not shares:
            continue
        j = max(shares)[1]
        u = unary_union([items[j][1].buffer(0.2), g.buffer(0.2)]).buffer(-0.2)
        if u.geom_type != "Polygon" or not u.is_valid:
            continue
        merged = _exact(u)
        others = [items[k][1] for k in range(len(items)) if k != j]
        if others and merged.intersection(unary_union(others)).area > p.gap_close_min_m2:
            continue  # the merge would cover a neighbour (its exterior closes round it)
        items[j][1] = merged
        n += 1
    return items, n
