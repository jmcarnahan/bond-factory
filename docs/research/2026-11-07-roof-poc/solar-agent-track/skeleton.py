"""Straight-skeleton roof edges for uniform-pitch hip/gable roofs.

Library: compas_cgal (LGPL-3.0 wrapper around CGAL Straight_skeleton_2), pip wheel, macOS ok.
All lengths in feet, areas in sq ft, polygon in local feet (x east, y north).

Tools meant to be called by the LLM agent (see agent_design.md):
  measure(polygon)
  split_footprint(polygon, line)
  hip_roof_edges(polygon_ft, pitch_rise, gable_edges=None)
  segment_to_footprint_match(solar_segments, polygon, origin)
"""
import math
import numpy as np
from shapely.geometry import Polygon, LineString, Point, MultiLineString
from shapely.ops import polygonize, unary_union, linemerge, split as shp_split
from compas_cgal.straight_skeleton_2 import interior_straight_skeleton

TOL = 1e-6


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _signed_area(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                     for i in range(len(p)))


def _line_isect(a, b, c, d):
    """Intersection of infinite lines ab and cd (None if parallel)."""
    r = (b[0] - a[0], b[1] - a[1]); s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    return (a[0] + t * r[0], a[1] + t * r[1])


def _inward_normal_ccw(p, q):
    dx, dy = q[0] - p[0], q[1] - p[1]
    L = math.hypot(dx, dy)
    return (-dy / L, dx / L)  # left of direction = inside for CCW


def _extend_for_gables(poly, gable_idx, D):
    """Push each gable edge outward by D along its outward normal, extending neighbours."""
    n = len(poly)
    lines = []  # per edge: (a, b) defining the (possibly shifted) infinite line
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if i in gable_idx:
            nx, ny = _inward_normal_ccw(a, b)
            a = (a[0] - nx * D, a[1] - ny * D); b = (b[0] - nx * D, b[1] - ny * D)
        lines.append((a, b))
    out = []
    for i in range(n):  # vertex i = intersection of edge i-1 and edge i
        if (i - 1) % n in gable_idx or i in gable_idx:
            p = _line_isect(*lines[(i - 1) % n], *lines[i])
            if p is None:  # parallel neighbours (rectangle): slide the vertex along its own edge line
                src = lines[(i - 1) % n] if (i - 1) % n not in gable_idx else lines[i]
                # vertex of the shifted gable edge lying on the non-gable neighbour's line
                g = lines[i] if i in gable_idx else lines[(i - 1) % n]
                p = _line_isect(*src, *g)
            out.append(p)
        else:
            out.append(poly[i])
    return out


# ----------------------------------------------------------------------------
# core
# ----------------------------------------------------------------------------
def hip_roof_edges(polygon_ft, pitch_rise, gable_edges=None, extend_ft=None):
    """Roof model for a uniform-pitch roof over `polygon_ft` (list of (x,y) feet).

    pitch_rise: rise per 12 run (e.g. 4 for 4/12).
    gable_edges: set of footprint edge indices (edge i = vertex i -> vertex i+1 of the INPUT
                 order) that are gable ends. They emit no eave and no facet; the sloped
                 boundary of the neighbouring facets along them is a rake.
    Returns dict(facets, edges, totals, slope_factor).
    """
    gable_edges = set(gable_edges or ())
    pts = [tuple(map(float, p)) for p in polygon_ft]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    # normalise to CCW; emap[j] = input edge index of CCW edge j
    if _signed_area(pts) < 0:
        rpts = pts[::-1]
        emap = [(n - 2 - j) % n for j in range(n)]
    else:
        rpts = pts; emap = list(range(n))
    inv = {emap[j]: j for j in range(n)}
    gab = {inv[g] for g in gable_edges}
    s = pitch_rise / 12.0
    sf = math.sqrt(1 + s * s)
    orig = Polygon(rpts)

    D = extend_ft if extend_ft is not None else 4 * max(orig.bounds[2] - orig.bounds[0],
                                                       orig.bounds[3] - orig.bounds[1])
    work = _extend_for_gables(rpts, gab, D) if gab else rpts
    V, idx, E, T = interior_straight_skeleton([[x, y, 0.0] for x, y in work], as_graph=False)
    row = {int(i): k for k, i in enumerate(idx)}
    segs = [LineString([V[row[int(a)]][:2], V[row[int(b)]][:2]]) for a, b in E]
    faces_all = list(polygonize(unary_union(segs)))

    facets = []
    fid_by_edge = {}
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
        # plane: z = s * inward distance from edge k's line
        def z(p, a=a, nx=nx, ny=ny):
            return s * ((p[0] - a[0]) * nx + (p[1] - a[1]) * ny)
        ring = list(face.exterior.coords)[:-1]
        xyz = [(x, y, z((x, y))) for x, y in ring]
        plan = face.area
        fid_by_edge[k] = len(facets)
        facets.append({
            "edge_index": emap[k],
            "polygon_xy": [(x, y) for x, y in ring],
            "polygon_xyz": xyz,
            "plan_area": plan,
            "area": plan * sf,
            "pitch_rise": pitch_rise,
            "pitch_degrees": math.degrees(math.atan(s)),
            "aspect_deg": math.degrees(math.atan2(-nx, -ny)) % 360,  # downslope compass bearing
            "_n": (nx, ny), "_poly": face, "_a": a,
        })

    edges = []
    # eaves
    for k in range(n):
        if k in gab:
            continue
        a, b = rpts[k], rpts[(k + 1) % n]
        L = math.dist(a, b)
        edges.append({"type": "eave", "polyline_xyz": [(a[0], a[1], 0.0), (b[0], b[1], 0.0)],
                      "plan_length": L, "length": L, "edge_index": emap[k]})
    # rakes: facet boundary segments lying on a gable edge
    for k in gab:
        g = LineString([rpts[k], rpts[(k + 1) % n]])
        for fi, f in enumerate(facets):
            c = f["_poly"].boundary.intersection(g.buffer(1e-4))
            ring = f["polygon_xy"]
            for i in range(len(ring)):
                p, q = ring[i], ring[(i + 1) % len(ring)]
                if g.distance(Point(p)) < 1e-4 and g.distance(Point(q)) < 1e-4 and math.dist(p, q) > 1e-6:
                    zp = f["polygon_xyz"][i][2]; zq = f["polygon_xyz"][(i + 1) % len(ring)][2]
                    pl = math.dist(p, q)
                    edges.append({"type": "rake", "polyline_xyz": [(p[0], p[1], zp), (q[0], q[1], zq)],
                                  "plan_length": pl, "length": math.hypot(pl, zq - zp),
                                  "edge_index": emap[k], "faces": [fi]})
    # interior edges: shared facet boundaries
    fl = list(enumerate(facets))
    for ii in range(len(fl)):
        for jj in range(ii + 1, len(fl)):
            i, fi = fl[ii]; j, fj = fl[jj]
            sh = fi["_poly"].boundary.intersection(fj["_poly"].boundary)
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
                zi = lambda t: s * ((t[0] - fi["_a"][0]) * fi["_n"][0] + (t[1] - fi["_a"][1]) * fi["_n"][1])
                zp, zq = zi(p), zi(q)
                pl = math.dist(p, q)
                ux, uy = (q[0] - p[0]) / pl, (q[1] - p[1]) / pl
                px, py = -uy, ux
                mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                cj = fj["_poly"].representative_point()
                if (cj.x - mid[0]) * px + (cj.y - mid[1]) * py < 0:
                    px, py = -px, -py
                ni, nj = fi["_n"], fj["_n"]
                convex = (nj[0] * px + nj[1] * py) < (ni[0] * px + ni[1] * py)
                parallel = abs(ni[0] * nj[1] - ni[1] * nj[0]) < 1e-6
                if (parallel or abs(zp - zq) < 1e-6) and convex:
                    typ = "ridge"
                elif convex:
                    typ = "hip"
                else:
                    typ = "valley"
                edges.append({"type": typ, "polyline_xyz": [(p[0], p[1], zp), (q[0], q[1], zq)],
                              "plan_length": pl, "length": math.hypot(pl, zq - zp), "faces": [i, j]})
    for f in facets:
        for k in ("_n", "_poly", "_a"):
            f.pop(k)
    tot = {t: 0.0 for t in ("eave", "rake", "ridge", "hip", "valley")}
    for e in edges:
        tot[e["type"]] += e["length"]
    totals = {f"{k}s_ft": v for k, v in tot.items()}
    totals["facet_area_sqft"] = sum(f["area"] for f in facets)
    totals["plan_area_sqft"] = sum(f["plan_area"] for f in facets)
    return {"slope_factor": sf, "pitch_rise": pitch_rise, "facets": facets, "edges": edges, "totals": totals}


# ----------------------------------------------------------------------------
# agent tools
# ----------------------------------------------------------------------------
def measure(polygon):
    """Basic geometry the agent may quote: area, perimeter, per-edge length and outward bearing."""
    pts = [tuple(p) for p in polygon]
    poly = Polygon(pts)
    ccw = _signed_area(pts) > 0
    n = len(pts)
    edges = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        # outward normal: right of direction for CCW, left for CW
        ox, oy = (dy, -dx) if ccw else (-dy, dx)
        edges.append({"index": i, "from": a, "to": b, "length_ft": math.hypot(dx, dy),
                      "outward_bearing_deg": math.degrees(math.atan2(ox, oy)) % 360})
    mrr = poly.minimum_rotated_rectangle
    return {"area_sqft": poly.area, "perimeter_ft": poly.length, "bounds": poly.bounds,
            "n_vertices": n, "orientation": "ccw" if ccw else "cw", "edges": edges,
            "min_rotated_rect_ft": sorted([math.dist(mrr.exterior.coords[0], mrr.exterior.coords[1]),
                                           math.dist(mrr.exterior.coords[1], mrr.exterior.coords[2])])}


def split_footprint(polygon, line):
    """Split the footprint by a cut line [(x,y),(x,y)] (extended as needed). Returns list of
    polygons (each a list of vertices), largest first, so the agent can treat blocks separately."""
    poly = Polygon(polygon)
    (x1, y1), (x2, y2) = line
    dx, dy = x2 - x1, y2 - y1
    L = 1e4 / max(math.hypot(dx, dy), 1e-9)
    cut = LineString([(x1 - dx * L, y1 - dy * L), (x2 + dx * L, y2 + dy * L)])
    parts = [g for g in shp_split(poly, cut).geoms]
    parts.sort(key=lambda g: -g.area)
    return [{"polygon": [tuple(c) for c in list(g.exterior.coords)[:-1]], "area_sqft": g.area} for g in parts]


def segment_to_footprint_match(solar_segments, polygon, origin, to_local):
    """Place Solar roofSegmentStats on the footprint frame.

    to_local(lng, lat, origin) -> (x, y) feet (see footprint.to_local).
    Returns per segment: local center, local bbox (ft), inside flag, distance to footprint,
    and flat/sloped classification (pitch < 2 deg = flat).
    """
    poly = Polygon(polygon)
    out = []
    for k, sg in enumerate(solar_segments):
        c = sg["center"]
        cx, cy = to_local(c["longitude"], c["latitude"], origin)
        bb = sg["boundingBox"]
        sw = to_local(bb["sw"]["longitude"], bb["sw"]["latitude"], origin)
        ne = to_local(bb["ne"]["longitude"], bb["ne"]["latitude"], origin)
        pt = Point(cx, cy)
        out.append({
            "segment": k, "center_ft": (cx, cy), "bbox_ft": (sw[0], sw[1], ne[0], ne[1]),
            "inside_footprint": poly.contains(pt), "dist_to_footprint_ft": poly.distance(pt),
            "pitch_degrees": sg["pitchDegrees"], "azimuth_degrees": sg["azimuthDegrees"],
            "area_sqft": sg["stats"]["areaMeters2"] * 10.7639,
            "ground_area_sqft": sg["stats"]["groundAreaMeters2"] * 10.7639,
            "form_hint": "flat" if sg["pitchDegrees"] < 2.0 else "sloped",
        })
    return out


def rect_fit(polygon):
    """Minimum rotated rectangle of a block (removes sub-2-ft jogs before hip_roof_edges).
    Returns (vertices, width_ft, length_ft, area_sqft)."""
    r = Polygon(polygon).minimum_rotated_rectangle
    c = [tuple(p) for p in list(r.exterior.coords)[:-1]]
    a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
    return c, min(a, b), max(a, b), r.area
