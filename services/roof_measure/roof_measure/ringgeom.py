"""Roof plan geometry that needs no CGAL: rings, rectangles, measuring, splitting, flat and shed blocks.

WHY a module of its own: ``skeleton.py`` needs ``compas_cgal`` (GPL, plan D3/D5). Everything here uses shapely only,
so the plane-based model (``model``, ``planes_model``) imports without CGAL; the hip and gable forms of
``block_geometry`` load ``skeleton`` on demand. ``skeleton.py`` re-exports these names, so older imports keep working.

Units: feet and square feet; plan coordinates x east, y north.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Polygon
from shapely.ops import split as shp_split

Pt = tuple[float, float]


# ----------------------------------------------------------------------------- helpers
def signed_area(p: list[Pt]) -> float:
    """Shoelace area; positive for counter-clockwise rings."""
    return 0.5 * sum(
        p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p))
    )


def open_ring(polygon: list[Any]) -> list[Pt]:
    """Vertices as float tuples without the closing duplicate or consecutive repeated vertices."""
    pts: list[Pt] = []
    for p in polygon:
        q = (float(p[0]), float(p[1]))
        if not pts or q != pts[-1]:  # a repeated vertex makes CGAL divide by zero
            pts.append(q)
    while len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


# ----------------------------------------------------------------------------- shed
def shed_roof_edges(polygon_ft: list[Any], pitch_rise: float, aspect_deg: float) -> dict[str, Any]:
    """One planar facet falling toward ``aspect_deg`` (compass); edges typed by orientation.

    The low edge(s) (outward normal within 45 deg of the downslope) are eaves, the high
    edge(s) (opposite) are ridges, the sides are rakes. The contract's shed rule, computed
    for any convex-ish polygon. Same return shape as :func:`hip_roof_edges`.
    """
    pts = open_ring(polygon_ft)
    if signed_area(pts) < 0:
        pts = pts[::-1]
    n = len(pts)
    s = pitch_rise / 12.0
    sf = math.sqrt(1 + s * s)
    a = math.radians(aspect_deg)
    d = (math.sin(a), math.cos(a))  # downslope unit vector (east, north)
    poly = Polygon(pts)
    # z is height above the lowest point: the vertex furthest along the downslope direction.
    low = max(p[0] * d[0] + p[1] * d[1] for p in pts)

    def z_at(p: Pt) -> float:
        return s * (low - (p[0] * d[0] + p[1] * d[1]))

    facet = {
        "edge_index": 0,
        "polygon_xy": list(pts),
        "polygon_xyz": [(x, y, z_at((x, y))) for x, y in pts],
        "plan_area": poly.area,
        "area": poly.area * sf,
        "pitch_rise": pitch_rise,
        "pitch_degrees": math.degrees(math.atan(s)),
        "aspect_deg": aspect_deg % 360,
        "plane": (s * low, -s * d[0], -s * d[1]),
    }
    edges: list[dict[str, Any]] = []
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        pl = math.dist(p, q)
        if pl < 1e-9:
            continue
        ox, oy = (q[1] - p[1]) / pl, -(q[0] - p[0]) / pl  # outward normal of a CCW edge
        dot = ox * d[0] + oy * d[1]
        typ = "eave" if dot > math.cos(math.radians(45)) else "ridge" if dot < -math.cos(math.radians(45)) else "rake"
        zp, zq = z_at(p), z_at(q)
        edges.append({"type": typ, "polyline_xyz": [(p[0], p[1], zp), (q[0], q[1], zq)], "plan_length": pl,
                      "length": math.hypot(pl, zq - zp), "edge_index": i, "faces": [0]})
    tot = {t: 0.0 for t in ("eave", "rake", "ridge", "hip", "valley")}
    for e in edges:
        tot[e["type"]] += e["length"]
    totals = {f"{k}s_ft": v for k, v in tot.items()}
    totals["facet_area_sqft"] = facet["area"]
    totals["plan_area_sqft"] = facet["plan_area"]
    return {"slope_factor": sf, "pitch_rise": pitch_rise, "facets": [facet], "edges": edges, "totals": totals}


# ----------------------------------------------------------------------------- agent tools
def measure(polygon: list[Any]) -> dict[str, Any]:
    """Area, perimeter, bounds and per edge length and outward bearing (compass degrees)."""
    pts = open_ring(polygon)
    poly = Polygon(pts)
    ccw = signed_area(pts) > 0
    n = len(pts)
    edges = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ox, oy = (dy, -dx) if ccw else (-dy, dx)
        edges.append({"index": i, "from": a, "to": b, "length_ft": math.hypot(dx, dy),
                      "outward_bearing_deg": math.degrees(math.atan2(ox, oy)) % 360})
    mrr = poly.minimum_rotated_rectangle
    c = list(mrr.exterior.coords)
    sides = sorted([math.dist(c[0], c[1]), math.dist(c[1], c[2])])
    return {"area_sqft": poly.area, "perimeter_ft": poly.length, "bounds": poly.bounds, "n_vertices": n,
            "orientation": "ccw" if ccw else "cw", "edges": edges, "min_rotated_rect_ft": sides}


def split_footprint(polygon: list[Any], line: list[Any]) -> list[dict[str, Any]]:
    """Split ``polygon`` by the infinite line through two points; largest part first."""
    poly = Polygon(open_ring(polygon))
    (x1, y1), (x2, y2) = line
    dx, dy = x2 - x1, y2 - y1
    k = 1e4 / max(math.hypot(dx, dy), 1e-9)
    cut = LineString([(x1 - dx * k, y1 - dy * k), (x2 + dx * k, y2 + dy * k)])
    parts = sorted(shp_split(poly, cut).geoms, key=lambda g: -g.area)
    return [{"polygon": [tuple(c) for c in list(g.exterior.coords)[:-1]], "area_sqft": g.area} for g in parts]


def rect_fit(polygon: list[Any]) -> tuple[list[Pt], float, float, float]:
    """Minimum rotated rectangle: ``(vertices CCW, short side, long side, area)``.

    WHY: LARIAC-style outlines carry 0.4-2 ft jogs that make a raw skeleton emit spurious
    hips and valleys (133 ft of hips and 51 ft of valleys versus 80 and 0 for the fitted
    rectangle on the sample building).
    """
    r = Polygon(open_ring(polygon)).minimum_rotated_rectangle
    c = [(float(x), float(y)) for x, y in list(r.exterior.coords)[:-1]]
    if signed_area(c) < 0:
        c = c[::-1]
    a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
    return c, min(a, b), max(a, b), r.area


# ----------------------------------------------------------------------------- per block dispatcher
def block_geometry(form: str, polygon: list[Any], pitch_rise: float, gable_edges: list[int] | None = None,
                   aspect_deg: float | None = None, ridge_fallback: bool = False) -> dict[str, Any]:
    """Facets and edges for one roof block, whatever its form.

    ``flat`` returns one facet (plane z = 0) and one ``outline`` edge per polygon edge (the
    model builder types those by neighbour). ``hip``/``gable`` use the straight skeleton (``skeleton.py``, CGAL) and
    ``shed`` a single plane. Same shape as :func:`hip_roof_edges`.
    """
    if form == "flat":
        pts = open_ring(polygon)
        if signed_area(pts) < 0:
            pts = pts[::-1]
        poly = Polygon(pts)
        n = len(pts)
        edges = []
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            pl = math.dist(p, q)
            if pl > 1e-9:
                edges.append({"type": "outline", "polyline_xyz": [(p[0], p[1], 0.0), (q[0], q[1], 0.0)],
                              "plan_length": pl, "length": pl, "edge_index": i, "faces": [0]})
        facet = {"edge_index": 0, "polygon_xy": list(pts), "polygon_xyz": [(x, y, 0.0) for x, y in pts],
                 "plan_area": poly.area, "area": poly.area, "pitch_rise": 0.0, "pitch_degrees": 0.0,
                 "aspect_deg": None, "plane": (0.0, 0.0, 0.0)}
        return {"slope_factor": 1.0, "pitch_rise": 0.0, "facets": [facet], "edges": edges, "totals": {}}
    if form == "shed":
        return shed_roof_edges(polygon, pitch_rise, 180.0 if aspect_deg is None else aspect_deg)
    if form in ("hip", "gable"):
        from .skeleton import hip_roof_edges

        return hip_roof_edges(polygon, pitch_rise, set(gable_edges or ()) if form == "gable" else None,
                              ridge_fallback=ridge_fallback and form == "gable")
    raise ValueError(f"unknown roof form {form!r}")
