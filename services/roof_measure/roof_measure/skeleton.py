"""Straight-skeleton roof geometry for uniform-pitch hip, gable and shed roofs.

WHY a skeleton: a hip or gable roof of uniform pitch is fully determined by its plan outline,
the pitch and which outline edges are gable ends. CGAL's straight skeleton gives the exact
ridge/hip/valley topology, so every length and area the model reports is computed, never
guessed (by us or by the Claude agent that calls these functions as tools).

Library: ``compas_cgal`` (wheel around CGAL ``Straight_skeleton_2``). CGAL's skeleton package is
GPL, which is acceptable for a server-side POC, not for a distributed binary. This is the ONLY module that needs it,
and only inside ``hip_roof_edges`` (``interior_straight_skeleton`` below imports it lazily). Everything CGAL-free
(rings, measure, split, rect_fit, flat and shed blocks, the ``block_geometry`` dispatcher) lives in ``ringgeom.py``
and is re-exported here.

Units: feet and square feet; plan coordinates x east, y north. Ported from the research
prototype (solar-agent-track/scripts/skeleton.py, 2026-11-07 12:26) and checked against the
closed form in ``tests/test_model_skeleton.py``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from shapely.geometry import LineString, MultiLineString, Point, Polygon
from shapely.ops import linemerge, polygonize, unary_union

from .ringgeom import (  # noqa: F401  (re-exported: the CGAL-free helpers moved to ringgeom; old imports keep working)
    Pt,
    block_geometry,
    measure,
    open_ring,
    rect_fit,
    shed_roof_edges,
    signed_area,
    split_footprint,
)
from .skeleton_guard import check_ring, safe_extension

log = logging.getLogger(__name__)


def interior_straight_skeleton(*args: Any, **kwargs: Any) -> Any:
    """CGAL's straight skeleton, imported on first use: importing this module needs no ``compas_cgal``."""
    from compas_cgal.straight_skeleton_2 import interior_straight_skeleton as cgal_skeleton

    return cgal_skeleton(*args, **kwargs)


# ----------------------------------------------------------------------------- helpers (CGAL path only)


def _line_isect(a: Pt, b: Pt, c: Pt, d: Pt) -> Pt | None:
    """Intersection of the infinite lines ab and cd; None when parallel."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    return (a[0] + t * r[0], a[1] + t * r[1])


def _inward_normal_ccw(p: Pt, q: Pt) -> Pt:
    dx, dy = q[0] - p[0], q[1] - p[1]
    length = math.hypot(dx, dy)
    return (-dy / length, dx / length)  # left of the direction is inside for a CCW ring


def _extend_for_gables(poly: list[Pt], gable_idx: set[int], dist: float) -> list[Pt]:
    """Push each gable edge outward by ``dist`` so the skeleton runs the ridge to that wall.

    WHY: a gable end has no eave, so no slope falls off it. Moving the edge far away makes the
    two facets either side of it reach it as full-height planes; we later clip back to the
    real outline and what lies on the original gable edge is the rake.
    """
    n = len(poly)
    lines: list[tuple[Pt, Pt]] = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if i in gable_idx:
            nx, ny = _inward_normal_ccw(a, b)
            a = (a[0] - nx * dist, a[1] - ny * dist)
            b = (b[0] - nx * dist, b[1] - ny * dist)
        lines.append((a, b))
    out: list[Pt] = []
    for i in range(n):
        if (i - 1) % n in gable_idx or i in gable_idx:
            p = _line_isect(*lines[(i - 1) % n], *lines[i])
            if p is None:
                src = lines[(i - 1) % n] if (i - 1) % n not in gable_idx else lines[i]
                g = lines[i] if i in gable_idx else lines[(i - 1) % n]
                p = _line_isect(*src, *g)
            out.append(p if p is not None else poly[i])
        else:
            out.append(poly[i])
    return out


# ----------------------------------------------------------------------------- hip / gable
def hip_roof_edges(polygon_ft: list[Any], pitch_rise: float, gable_edges: set[int] | list[int] | None = None,
                   extend_ft: float | None = None, ridge_fallback: bool = False) -> dict[str, Any]:
    """Facets and typed edges of a uniform-pitch roof over ``polygon_ft``.

    ``ridge_fallback``: when the gable ends cannot be extended on this outline, draw the gable from its ridge line
    (``skeleton_gable.ridge_gable``) instead of raising; off by default, so nothing that builds today changes.
    ``pitch_rise`` is inches of rise per 12 of run. ``gable_edges`` are indices of INPUT polygon
    edges (edge i = vertex i to i+1) that are gable ends: they get no eave and no facet and the
    sloped boundary of the facets along them is a rake.

    Returns ``{slope_factor, pitch_rise, facets, edges, totals, notes}`` (``notes``: sentences about changes made). Each facet has ``polygon_xy``,
    ``polygon_xyz`` (z = height above the eave plane), ``plan_area``, ``area`` (true),
    ``aspect_deg`` (compass downslope), ``edge_index`` and ``plane`` (z = c0 + c1 x + c2 y).
    Each edge has ``type`` (eave|rake|ridge|hip|valley), a two point ``polyline_xyz``,
    ``plan_length``, ``length`` (true 3D) and ``faces`` (indices into ``facets``).
    """
    gable = set(gable_edges or ())
    pts = open_ring(polygon_ft)
    n = len(pts)
    if n < 3:
        raise ValueError("polygon needs at least 3 vertices")
    if signed_area(pts) < 0:  # normalise to CCW; emap[j] = input edge index of CCW edge j
        rpts = pts[::-1]
        emap = [(n - 2 - j) % n for j in range(n)]
    else:
        rpts = pts
        emap = list(range(n))
    inv = {emap[j]: j for j in range(n)}
    gab = {inv[g] for g in gable if g in inv}
    s = pitch_rise / 12.0
    sf = math.sqrt(1 + s * s)
    check_ring(rpts, "outline")  # a bad ring is undefined behaviour in CGAL: refuse it here
    orig = Polygon(rpts)

    big = extend_ft if extend_ft is not None else 4 * max(orig.bounds[2] - orig.bounds[0],
                                                          orig.bounds[3] - orig.bounds[1])
    try:
        work, used = safe_extension(rpts, gab, big, _extend_for_gables) if gab else (rpts, big)
    except ValueError:
        if not (ridge_fallback and gab):
            raise
        from .skeleton_gable import ridge_gable

        return ridge_gable(polygon_ft, pitch_rise, gable)
    notes: list[str] = []
    if used != big:  # a silent change of geometry is not allowed: say it
        notes.append(f"Gable ends were extended by {used:.0f} ft instead of {big:.0f} ft because the sides next to "
                     "them converge; check the rakes.")
    check_ring(work, "skeleton input")  # the only native call below must never see an invalid ring
    verts, idx, skel_edges, _ = interior_straight_skeleton([[x, y, 0.0] for x, y in work], as_graph=False)
    row = {int(i): k for k, i in enumerate(idx)}
    segs = [LineString([verts[row[int(a)]][:2], verts[row[int(b)]][:2]]) for a, b in skel_edges]
    faces_all = list(polygonize(unary_union(segs)))

    facets: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []  # per facet: shapely face, inward normal, anchor point
    for k in range(n):
        if k in gab:
            continue
        a, b = work[k], work[(k + 1) % n]
        nx, ny = _inward_normal_ccw(a, b)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        probe = Point(mid[0] + 1e-5 * nx, mid[1] + 1e-5 * ny)
        face = next((f for f in faces_all if f.contains(probe)), None)
        if face is None:
            continue
        if gab:
            face = face.intersection(orig)
            if face.is_empty or face.area < 1e-6:
                continue
            if face.geom_type != "Polygon":
                face = max(face.geoms, key=lambda g: g.area)

        def z_at(p: Pt, a: Pt = a, nx: float = nx, ny: float = ny) -> float:
            return s * ((p[0] - a[0]) * nx + (p[1] - a[1]) * ny)

        ring = list(face.exterior.coords)[:-1]
        facets.append({
            "edge_index": emap[k],
            "polygon_xy": [(x, y) for x, y in ring],
            "polygon_xyz": [(x, y, z_at((x, y))) for x, y in ring],
            "plan_area": face.area,
            "area": face.area * sf,
            "pitch_rise": pitch_rise,
            "pitch_degrees": math.degrees(math.atan(s)),
            "aspect_deg": math.degrees(math.atan2(-nx, -ny)) % 360,  # downslope compass bearing
            "plane": (-s * (a[0] * nx + a[1] * ny), s * nx, s * ny),
        })
        meta.append({"poly": face, "n": (nx, ny), "a": a, "k": k})

    edges: list[dict[str, Any]] = []
    for fi, m in enumerate(meta):  # eaves: the outline edge each facet starts from
        k = m["k"]
        a, b = rpts[k], rpts[(k + 1) % n]
        length = math.dist(a, b)
        edges.append({"type": "eave", "polyline_xyz": [(a[0], a[1], 0.0), (b[0], b[1], 0.0)],
                      "plan_length": length, "length": length, "edge_index": emap[k], "faces": [fi]})
    for k in gab:  # rakes: facet boundary segments lying on a gable edge
        g = LineString([rpts[k], rpts[(k + 1) % n]])
        for fi, f in enumerate(facets):
            ring = f["polygon_xy"]
            for i in range(len(ring)):
                p, q = ring[i], ring[(i + 1) % len(ring)]
                if g.distance(Point(p)) < 1e-4 and g.distance(Point(q)) < 1e-4 and math.dist(p, q) > 1e-6:
                    zp = f["polygon_xyz"][i][2]
                    zq = f["polygon_xyz"][(i + 1) % len(ring)][2]
                    pl = math.dist(p, q)
                    edges.append({"type": "rake", "polyline_xyz": [(p[0], p[1], zp), (q[0], q[1], zq)],
                                  "plan_length": pl, "length": math.hypot(pl, zq - zp),
                                  "edge_index": emap[k], "faces": [fi]})
    edges.extend(_interior_edges(meta, s))

    tot = {t: 0.0 for t in ("eave", "rake", "ridge", "hip", "valley")}
    for e in edges:
        tot[e["type"]] += e["length"]
    totals = {f"{k}s_ft": v for k, v in tot.items()}
    totals["facet_area_sqft"] = sum(f["area"] for f in facets)
    totals["plan_area_sqft"] = sum(f["plan_area"] for f in facets)
    return {"slope_factor": sf, "pitch_rise": pitch_rise, "facets": facets, "edges": edges, "totals": totals,
            "notes": notes}


def _interior_edges(meta: list[dict[str, Any]], s: float) -> list[dict[str, Any]]:
    """Ridge / hip / valley edges: shared boundaries between two facets of the skeleton."""
    out: list[dict[str, Any]] = []
    for i in range(len(meta)):
        for j in range(i + 1, len(meta)):
            mi, mj = meta[i], meta[j]
            sh = mi["poly"].boundary.intersection(mj["poly"].boundary)
            if sh.is_empty:
                continue
            geoms = [sh] if sh.geom_type == "LineString" else \
                [g for g in getattr(sh, "geoms", []) if g.geom_type == "LineString"]
            if not geoms:
                continue
            merged = linemerge(MultiLineString(geoms)) if len(geoms) > 1 else geoms[0]
            for ln in ([merged] if merged.geom_type == "LineString" else list(merged.geoms)):
                if ln.length < 1e-6:
                    continue
                p, q = ln.coords[0][:2], ln.coords[-1][:2]
                a, (nx, ny) = mi["a"], mi["n"]

                def zi(t: Pt, a: Pt = a, nx: float = nx, ny: float = ny) -> float:
                    return s * ((t[0] - a[0]) * nx + (t[1] - a[1]) * ny)

                zp, zq = zi(p), zi(q)
                pl = math.dist(p, q)
                ux, uy = (q[0] - p[0]) / pl, (q[1] - p[1]) / pl
                px, py = -uy, ux
                mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                cj = mj["poly"].representative_point()
                if (cj.x - mid[0]) * px + (cj.y - mid[1]) * py < 0:
                    px, py = -px, -py
                ni, nj = mi["n"], mj["n"]
                convex = (nj[0] * px + nj[1] * py) < (ni[0] * px + ni[1] * py)
                parallel = abs(ni[0] * nj[1] - ni[1] * nj[0]) < 1e-6
                if (parallel or abs(zp - zq) < 1e-6) and convex:
                    typ = "ridge"
                elif convex:
                    typ = "hip"
                else:
                    typ = "valley"
                out.append({"type": typ, "polyline_xyz": [(p[0], p[1], zp), (q[0], q[1], zq)],
                            "plan_length": pl, "length": math.hypot(pl, zq - zp), "faces": [i, j]})
    return out
