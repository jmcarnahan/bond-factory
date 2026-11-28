"""Roof-edge outline: the regularised county footprint, each side moved to the roof edge the edge finder measures
(edge_finder.py), then regularised. Metres, building frame."""

from __future__ import annotations

from typing import Any

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon

from .edge_finder import clamp_offsets, find_roof_edge, support_area
from .params import EngineParams
from .ringfit import regularise_ring


def _ccw(poly: Polygon) -> Polygon:
    return poly if poly.exterior.is_ccw else Polygon(list(poly.exterior.coords)[::-1])


def _regular_footprint(footprint: Polygon, theta: float, p: EngineParams) -> Polygon:
    """The footprint orthogonalised to the wall axes (or lightly simplified when that distorts it), CCW."""
    fp = _ccw(Polygon(footprint.exterior))
    ring = regularise_ring(fp, theta, snap_deg=p.footprint_snap_deg, min_edge=p.ring_min_edge_m, tol=p.footprint_tol_m)
    if ring is None or ring.is_empty or ring.geom_type != "Polygon" or not (p.footprint_area_lo * fp.area < ring.area < p.footprint_area_hi * fp.area):
        ring = fp.simplify(p.footprint_simplify_m)
    return _ccw(ring)


def _finish(outline, theta: float, p: EngineParams) -> Any:
    if outline.geom_type != "Polygon":
        return outline.simplify(p.final_tol_m)
    oc = Polygon(outline.exterior)
    if p.outline_close_m > 0:  # slits narrower than this are not a roof shape
        closed = oc.buffer(p.outline_close_m, join_style=2).buffer(-p.outline_close_m, join_style=2)
        if closed.geom_type == "Polygon" and closed.is_valid and closed.area < 1.05 * oc.area:
            oc = Polygon(closed.exterior)
    try:
        reg = regularise_ring(oc, theta, snap_deg=p.final_snap_deg, min_edge=p.final_min_edge_m, tol=p.final_tol_m)
    except Exception:  # noqa: BLE001 - a degenerate ring falls back to the plain simplify
        reg = None
    if reg is not None and reg.geom_type == "Polygon" and not reg.is_empty and p.final_area_lo * oc.area < reg.area < p.final_area_hi * oc.area:
        return reg
    return oc.simplify(p.final_tol_m)


def build_outline(q: np.ndarray, qlab: np.ndarray, planes: list, footprint: Polygon, theta: float, county: bool,
                  context: np.ndarray | None, roof_xyz: np.ndarray, p: EngineParams) -> tuple[Polygon, dict[str, Any]]:
    """Roof-edge polygon for the roof points ``q`` (n, 3) assigned to ``planes`` (labels ``qlab``) and the given
    ``footprint``. ``context`` is the wide cloud (x, y, z, class) in the building frame (None: ``roof_xyz`` stands
    in). Returns (polygon, diagnostics)."""
    if len(q) == 0:
        return footprint, {"outline_source": "footprint (no points)"}
    ring = _regular_footprint(footprint, theta, p)
    res = find_roof_edge(context, roof_xyz, q, qlab, planes, ring, county, p)
    outline = _finish(res.polygon, theta, p)
    diag: dict[str, Any] = {"outline_source": "points+footprint", **res.diagnostics}
    if outline.is_empty or outline.geom_type != "Polygon" or outline.area <= 0:  # the offset ring collapsed: never refuse
        outline = ring  # for that, draw the regular (unregistered) ring and say so
        diag["edge_fallback"] = "regular ring"
    diag.update({"edge_offset_measured_m": [None if v is None else round(v, 2) for v in res.measured],
                 "edge_offset_applied_m": [round(v, 2) for v in clamp_offsets(res.offsets, county, res.sources, p)],
                 "edge_strips": dict(sorted(res.rejected.items())),
                 "support_area_m2": round(support_area(q, affinity.translate(footprint, *res.shift), p), 1)})  # registered
    return outline, diag
