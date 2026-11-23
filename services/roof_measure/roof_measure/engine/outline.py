"""Roof-edge outline: the regularised county footprint, each edge pushed out to the measured roof edge (overhang),
trimmed where no roof points exist, plus large roof parts the footprint misses. Metres, building frame."""

from __future__ import annotations

from typing import Any

import numpy as np
import shapely
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Polygon

from .params import DEFAULT, EngineParams
from .raster import trace_polys
from .ringfit import regularise_ring


def support_polygon(q: np.ndarray, footprint: Polygon, p: EngineParams) -> Polygon:
    """Raster support of the roof points (cells within 0.5 m of a point, eroded), within footprint + 1 m."""
    h = p.support_h_m
    fb = footprint.buffer(p.support_buffer_m)
    minx, miny, maxx, maxy = fb.bounds
    xs = np.arange(minx, maxx, h) + h / 2
    ys = np.arange(miny, maxy, h) + h / 2
    gx, gy = np.meshgrid(xs, ys)
    cells = np.c_[gx.ravel(), gy.ravel()]
    d, _ = cKDTree(q[:, :2]).query(cells, k=1)
    d = d.reshape(gx.shape)
    m1 = d <= p.support_reach_m
    e = ndi.distance_transform_edt(np.pad(m1, 4))[4:-4, 4:-4]
    mask = (e > p.support_erode_m / h) & shapely.contains_xy(fb, gx, gy)
    filled = ndi.binary_fill_holes(mask)
    lab, nl = ndi.label(filled & ~mask)
    for i in range(1, nl + 1):
        if (lab == i).sum() * h * h < p.support_hole_m2:
            mask[lab == i] = True
    polys = [g for g in trace_polys(mask, minx, miny, h) if g.area > p.support_part_m2]
    return shapely.union_all(polys) if polys else Polygon()


def local_spacing(q: np.ndarray, sup: Polygon, a: np.ndarray, b: np.ndarray, p: EngineParams) -> float:
    """Mean spacing (m) of the returns along edge a-b: 1 / sqrt(density) of the support within ``spacing_strip_m`` of it
    (one value per edge, so scan-line banding on one side does not leak into the others)."""
    zone = LineString([a, b]).buffer(p.spacing_strip_m).intersection(sup)
    if zone.is_empty or zone.area < 1.0:
        zone = sup
    n = int(shapely.contains_xy(zone, q[:, 0], q[:, 1]).sum())
    dens = n / max(zone.area, 1e-6)
    return float(np.clip(1.0 / np.sqrt(max(dens, 1e-6)), p.spacing_min_m, p.spacing_max_m))


def measure_edge_overhang(sup: Polygon, a: np.ndarray, b: np.ndarray, n: np.ndarray, p: EngineParams) -> float | None:
    """Outermost support position (m) along ``edge_rays`` rays normal to edge a-b (outward ``n``); their ``edge_ray_quantile``, or None."""
    d = b - a
    vals = []
    ts = np.arange(-p.edge_ray_in_m, p.edge_ray_out_m, p.edge_ray_step_m)
    for s in np.linspace(p.edge_ray_lo, 1.0 - p.edge_ray_lo, p.edge_rays):
        m = a + d * s
        pts = m[None, :] + ts[:, None] * n[None, :]
        ins = shapely.contains_xy(sup, pts[:, 0], pts[:, 1])
        if ins.any():
            vals.append(ts[np.nonzero(ins)[0].max()] + p.edge_ray_step_m / 2)
    if len(vals) < 3:
        return None
    return float(np.quantile(vals, p.edge_ray_quantile))


def offset_polygon(ring: Polygon, dist: list[float], p: EngineParams = DEFAULT) -> Polygon:
    """Polygon (CCW) with per-edge outward offsets ``dist[i]``; consecutive offset lines are intersected."""
    c = np.array(ring.exterior.coords)[:-1]
    n = len(c)
    lines = []
    for i in range(n):
        a, b = c[i], c[(i + 1) % n]
        d = b - a
        u = d / np.hypot(*d)
        nrm = np.array([u[1], -u[0]])  # outward for CCW
        lines.append((a + nrm * dist[i], u, nrm))
    verts = []
    for i in range(n):
        p1, u1, n1 = lines[i - 1]
        p2, u2, n2 = lines[i]
        a = np.array([u1, -u2]).T
        if abs(np.linalg.det(a)) < p.offset_parallel_det:
            verts.append(c[i] + (n1 * dist[i - 1] + n2 * dist[i]) / 2)
        else:
            t = np.linalg.solve(a, p2 - p1)
            v = p1 + t[0] * u1
            if np.hypot(*(v - c[i])) > p.offset_corner_max_m:
                v = c[i] + (n1 * dist[i - 1] + n2 * dist[i]) / 2
            verts.append(v)
    out = Polygon(verts)
    if not out.is_valid:
        out = out.buffer(0)
        if out.geom_type == "MultiPolygon":
            out = max(out.geoms, key=lambda g: g.area)
    return out


def _ccw(poly: Polygon) -> Polygon:
    return poly if poly.exterior.is_ccw else Polygon(list(poly.exterior.coords)[::-1])


def _regular_footprint(footprint: Polygon, theta: float, p: EngineParams) -> Polygon:
    """The footprint orthogonalised to the wall axes (or lightly simplified when that distorts it), CCW."""
    fp = _ccw(Polygon(footprint.exterior))
    ring = regularise_ring(fp, theta, snap_deg=p.footprint_snap_deg, min_edge=p.ring_min_edge_m, tol=p.footprint_tol_m)
    if ring is None or ring.is_empty or ring.geom_type != "Polygon" or not (p.footprint_area_lo * fp.area < ring.area < p.footprint_area_hi * fp.area):
        ring = fp.simplify(p.footprint_simplify_m)
    return _ccw(ring)


def _measure_overhangs(ring: Polygon, sup: Polygon, q: np.ndarray, p: EngineParams) -> list[float | None]:
    """Measured overhang per ring edge (None for edges shorter than ``edge_min_len_m`` or without enough rays).
    The support boundary sits ``support_gap_share`` x spacing less ``support_edge_bias_m`` from the true roof edge
    (it moves inward as the returns thin out), so each edge is corrected by that amount."""
    c = np.array(ring.exterior.coords)[:-1]
    out: list[float | None] = []
    for i in range(len(c)):
        a, b = c[i], c[(i + 1) % len(c)]
        length = float(np.hypot(*(b - a)))
        if length < p.edge_min_len_m:
            out.append(None)
            continue
        u = (b - a) / length
        raw = measure_edge_overhang(sup, a, b, np.array([u[1], -u[0]]), p)
        out.append(None if raw is None else raw + p.support_gap_share * local_spacing(q, sup, a, b, p) - p.support_edge_bias_m)
    return out


def _offset_distances(measured: list[float | None], scale: float, p: EngineParams) -> list[float]:
    known = [v for v in measured if v is not None]
    dflt = float(np.median(known)) if known else p.overhang_default_m

    def sc(v: float) -> float:
        return v * scale if v > 0 else v

    return [min(p.overhang_cap_m, max(p.overhang_floor_m, sc(v))) if v is not None
            else min(p.overhang_cap_m, max(0.0, sc(dflt))) for v in measured]


def _trim_notches(o0: Polygon, sup: Polygon, diag: dict[str, Any], p: EngineParams) -> Polygon:
    """Cut out thick parts of ``o0`` (> 1.5 m2, >= 0.8 m wide) where no roof points exist at all."""
    miss = o0.difference(sup.buffer(p.notch_support_buffer_m))
    if miss.is_empty:
        return o0
    cut = []
    for m in (miss.geoms if hasattr(miss, "geoms") else [miss]):
        if (m.geom_type == "Polygon" and m.area > p.notch_min_area_m2
                and not m.buffer(-p.notch_min_width_m / 2).is_empty):
            cut.append(m.buffer(p.notch_support_buffer_m).intersection(o0))
    if not cut:
        return o0
    core = o0.difference(shapely.union_all(cut).buffer(-p.notch_core_shrink_m))
    if core.geom_type == "MultiPolygon":
        core = max(core.geoms, key=lambda x: x.area)
    diag["trimmed_parts"] = len(cut)
    return core


def _extra_parts(sup: Polygon, o0: Polygon, p: EngineParams) -> list:
    """Supported roof parts well outside ``o0`` (wings the footprint misses), grown to the support."""
    zone = sup.difference(o0.buffer(p.extra_zone_buffer_m))
    extras = []
    if zone.is_empty:
        return extras
    for g in (zone.geoms if hasattr(zone, "geoms") else [zone]):
        if g.geom_type == "Polygon" and g.area > p.extra_min_area_m2:
            g2 = g.buffer(-p.extra_open_m, join_style=2).buffer(p.extra_open_m, join_style=2)
            if not g2.is_empty:
                extras.append(g2.buffer(p.extra_zone_buffer_m, join_style=2).intersection(sup.buffer(p.extra_support_buffer_m)))
    return extras


def _single_polygon(geom, p: EngineParams) -> Any:
    """Collapse a MultiPolygon: keep the parts above 3 m2 (or the largest), bridging any that stay apart."""
    if geom.geom_type == "MultiPolygon":
        big = [g for g in geom.geoms if g.area > p.min_part_area_m2]
        geom = shapely.union_all(big) if big else max(geom.geoms, key=lambda g: g.area)
    if geom.geom_type == "MultiPolygon":
        geom = shapely.union_all([g.buffer(p.bridge_m) for g in geom.geoms]).buffer(-p.bridge_m)
    return geom


def _finish(outline, theta: float, p: EngineParams) -> Any:
    if outline.geom_type != "Polygon":
        return outline.simplify(p.final_tol_m)
    oc = Polygon(outline.exterior)
    if p.outline_close_m > 0:  # slits narrower than this are not a roof shape (they only open when a cut and a part meet)
        closed = oc.buffer(p.outline_close_m, join_style=2).buffer(-p.outline_close_m, join_style=2)
        if closed.geom_type == "Polygon" and closed.is_valid and closed.area < 1.05 * oc.area:
            oc = Polygon(closed.exterior)
    try:
        reg = regularise_ring(oc, theta, snap_deg=p.final_snap_deg, min_edge=p.ring_min_edge_m, tol=p.final_tol_m)
    except Exception:  # noqa: BLE001 - a degenerate ring falls back to the plain simplify
        reg = None
    if reg is not None and reg.geom_type == "Polygon" and not reg.is_empty and p.final_area_lo * oc.area < reg.area < p.final_area_hi * oc.area:
        return reg
    return oc.simplify(p.final_tol_m)


def build_outline(q: np.ndarray, footprint: Polygon, theta: float, scale: float,
                  p: EngineParams) -> tuple[Polygon, dict[str, Any]]:
    """Roof-edge polygon for roof points ``q`` (n, 3) and the wall-line ``footprint``; ``scale`` multiplies the
    measured overhang. Returns (polygon, diagnostics)."""
    sup = support_polygon(q, footprint, p)
    diag: dict[str, Any] = {"outline_source": "points+footprint"}
    if sup.is_empty:
        return footprint, {"outline_source": "footprint (no points)"}
    ring = _regular_footprint(footprint, theta, p)
    measured = _measure_overhangs(ring, sup, q, p)
    dist = _offset_distances(measured, scale, p)
    o0 = offset_polygon(ring, dist, p)
    if o0.is_empty or not (p.offset_area_lo * ring.area < o0.area < p.offset_area_hi * ring.area):
        known = [v for v in measured if v is not None]
        dflt = float(np.median(known)) if known else p.overhang_default_m
        o0 = ring.buffer(min(p.overhang_cap_m, max(0.0, dflt)), join_style=2)
    core = _trim_notches(o0, sup, diag, p)
    extras = _extra_parts(sup, o0, p)
    outline = shapely.union_all([core] + extras) if extras else core
    outline = _finish(_single_polygon(outline, p), theta, p)
    diag.update({"overhang_measured_m": [None if v is None else round(v, 2) for v in measured],
                 "overhang_applied_m": [round(v, 2) for v in dist],
                 "support_area_m2": round(float(sup.area), 1), "extra_parts": len(extras),
                 "footprint_area_m2": round(float(footprint.area), 1), "outline_area_m2": round(float(outline.area), 1)})
    return outline, diag


def overhang_per_side(footprint: Polygon, outline: Polygon) -> list[float]:
    """Measured distance (m) from each long (>= 3 m) footprint edge to the outline edge outward."""
    res = []
    c = np.array(footprint.exterior.coords)
    ccw = footprint.exterior.is_ccw
    for i in range(len(c) - 1):
        a, b = c[i], c[i + 1]
        d = b - a
        length = np.hypot(*d)
        if length < 3.0:
            continue
        u = d / length
        n = np.array([u[1], -u[0]]) if ccw else np.array([-u[1], u[0]])
        vals = []
        for s in (0.3, 0.5, 0.7):
            m = a + d * s
            ray = LineString([m - n * 1.5, m + n * 2.5])
            inter = ray.intersection(outline.exterior if outline.geom_type == "Polygon" else outline.boundary)
            pts = []
            if not inter.is_empty:
                for g in (list(inter.geoms) if hasattr(inter, "geoms") else [inter]):
                    if g.geom_type == "Point":
                        pts.append(float(np.dot(np.array(g.coords[0]) - m, n)))
            if pts:
                vals.append(max(pts))
        if vals:
            res.append(round(float(np.median(vals)), 2))
    return res
