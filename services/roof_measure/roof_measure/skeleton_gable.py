"""A gable drawn from its ridge line, for outlines the straight-skeleton extension cannot take.

``skeleton.hip_roof_edges`` makes a gable by pushing the gable ends far out and running CGAL's skeleton; on an outline
whose sides next to a gable end converge (a footprint clipped by its neighbours) that raises ``ValueError``. This is
the fallback that never fails on a simple polygon: the ridge runs along the gable ends' outward direction through the
middle of the outline, each side of it is one plane falling away from the ridge at the pitch, and the outline's own
edges are typed by which way they face (toward the slope: eave, along the ridge direction: rake). It is used only when
the caller asks for it (``ridge_fallback=True``) and the skeleton extension has refused the outline, so every outline
that builds today builds the same.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import linemerge

from .ringgeom import Pt, open_ring, signed_area

NOTE = "Gable drawn from its ridge line because the outline's sides converge toward the gable ends."
TOL_FT = 1e-4
BIG = 1e4


def _bearing(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, dy)) % 360.0


def ridge_gable(polygon_ft: list[Any], pitch_rise: float, gable_edges: set[int] | list[int]) -> dict[str, Any]:
    """Facets and edges (the shape ``hip_roof_edges`` returns) of a two-plane gable over any simple polygon.

    ``gable_edges`` are input edge indices; their length-weighted outward direction is the ridge direction. Raises
    ValueError when no gable edge is given or the outline is degenerate.
    """
    pts = open_ring(polygon_ft)
    n = len(pts)
    if n < 3:
        raise ValueError("polygon needs at least 3 vertices")
    if signed_area(pts) < 0:
        pts = pts[::-1]
        emap = [(n - 2 - j) % n for j in range(n)]
    else:
        emap = list(range(n))
    inv = {emap[j]: j for j in range(n)}
    gab = {inv[g] for g in gable_edges if g in inv}
    if not gab:
        raise ValueError("a gable needs gable_edges")
    orig = Polygon(pts)
    if not orig.is_valid or orig.area <= 1e-6:
        raise ValueError("the outline is not a simple polygon")
    # the ridge runs from one gable end to the other: along the (mean) outward normal of the gable edges
    rx = ry = 0.0
    ref = None
    for k in gab:
        a, b = pts[k], pts[(k + 1) % n]
        ox, oy = b[1] - a[1], -(b[0] - a[0])  # outward normal of a CCW edge, length = edge length
        if ref is None:
            ref = (ox, oy)
        if ox * ref[0] + oy * ref[1] < 0:  # the two gable ends point opposite ways: flip onto one axis
            ox, oy = -ox, -oy
        rx, ry = rx + ox, ry + oy
    length = math.hypot(rx, ry)
    if length < 1e-9:
        raise ValueError("the gable edges do not give a ridge direction")
    ux, uy = rx / length, ry / length  # ridge direction
    nx, ny = -uy, ux  # across the ridge
    proj = [p[0] * nx + p[1] * ny for p in pts]
    c = (min(proj) + max(proj)) / 2.0
    w = (max(proj) - min(proj)) / 2.0
    s = pitch_rise / 12.0
    sf = math.sqrt(1 + s * s)
    halves = []  # (polygon, sign): sign +1 falls toward +n
    for sign in (1, -1):
        box = Polygon([(nx * c - ux * BIG, ny * c - uy * BIG), (nx * c + ux * BIG, ny * c + uy * BIG),
                       (nx * (c + sign * BIG) + ux * BIG, ny * (c + sign * BIG) + uy * BIG),
                       (nx * (c + sign * BIG) - ux * BIG, ny * (c + sign * BIG) - uy * BIG)])
        part = orig.intersection(box)
        parts = [g for g in (part.geoms if hasattr(part, "geoms") else [part]) if g.geom_type == "Polygon" and g.area > 1e-6]
        halves.extend((g, sign) for g in sorted(parts, key=lambda g: -g.area))
    if not halves:
        raise ValueError("the outline has no area either side of the ridge")

    def z_at(p: Pt, sign: int) -> float:
        return s * (w - sign * (p[0] * nx + p[1] * ny - c))

    facets: list[dict[str, Any]] = []
    for g, sign in halves:
        ring = list(g.exterior.coords)[:-1]
        if signed_area(ring) < 0:
            ring = ring[::-1]
        facets.append({
            "edge_index": 0, "polygon_xy": [(x, y) for x, y in ring],
            "polygon_xyz": [(x, y, z_at((x, y), sign)) for x, y in ring],
            "plan_area": g.area, "area": g.area * sf, "pitch_rise": pitch_rise,
            "pitch_degrees": math.degrees(math.atan(s)), "aspect_deg": _bearing(sign * nx, sign * ny),
            "plane": (s * (w + sign * c), -sign * s * nx, -sign * s * ny)})
    edges: list[dict[str, Any]] = []
    outline = [LineString([pts[k], pts[(k + 1) % n]]) for k in range(n)]
    for fi, ((g, sign), f) in enumerate(zip(halves, facets, strict=True)):
        ring = f["polygon_xy"]
        for i in range(len(ring)):
            p, q = ring[i], ring[(i + 1) % len(ring)]
            pl = math.dist(p, q)
            if pl < 1e-6:
                continue
            mid = Point((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            k = next((k for k in range(n) if outline[k].distance(mid) < TOL_FT), None)
            if k is None:
                continue  # an interior edge: the ridge, added once below
            ox, oy = pts[(k + 1) % n][1] - pts[k][1], -(pts[(k + 1) % n][0] - pts[k][0])
            ol = math.hypot(ox, oy) or 1.0
            across = abs((ox * nx + oy * ny) / ol)
            typ = "eave" if across >= math.cos(math.radians(45)) else "rake"
            zp, zq = f["polygon_xyz"][i][2], f["polygon_xyz"][(i + 1) % len(ring)][2]
            edges.append({"type": typ, "polyline_xyz": [(p[0], p[1], zp), (q[0], q[1], zq)], "plan_length": pl,
                          "length": math.hypot(pl, zq - zp), "edge_index": emap[k], "faces": [fi]})
    if len(halves) >= 2:
        shared = halves[0][0].boundary.intersection(halves[1][0].boundary)
        lines = [g for g in (shared.geoms if hasattr(shared, "geoms") else [shared]) if g.geom_type == "LineString"]
        merged = linemerge(lines) if lines else None
        for ln in ([] if merged is None else ([merged] if merged.geom_type == "LineString" else list(merged.geoms))):
            if ln.length < 1e-6:
                continue
            p, q = ln.coords[0][:2], ln.coords[-1][:2]
            z = s * w
            edges.append({"type": "ridge", "polyline_xyz": [(p[0], p[1], z), (q[0], q[1], z)],
                          "plan_length": ln.length, "length": ln.length, "faces": [0, 1]})
    tot = {t: 0.0 for t in ("eave", "rake", "ridge", "hip", "valley")}
    for e in edges:
        tot[e["type"]] += e["length"]
    totals = {f"{k}s_ft": v for k, v in tot.items()}
    totals["facet_area_sqft"] = sum(f["area"] for f in facets)
    totals["plan_area_sqft"] = sum(f["plan_area"] for f in facets)
    return {"slope_factor": sf, "pitch_rise": pitch_rise, "facets": facets, "edges": edges, "totals": totals,
            "notes": [NOTE]}
