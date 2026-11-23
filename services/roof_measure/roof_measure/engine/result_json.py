"""The harness result format (the reference's ``result.json``): one dict, rounded the same way, no wall time."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shapely.geometry import Polygon

from .cleanup import valid_polygon

if TYPE_CHECKING:
    from .types import Edge, EngineResult, Facet

METHOD = "own-raster"  # kept from the reference so harness baselines and diffs line up
VERSION = "roof-engine 0.1 (port of own-raster 0.1 2026-11-22)"


def _ring(poly) -> list[list[float]]:
    """The exterior ring rounded to the millimetre; rounding can fold a sub-millimetre pinch into a self-intersection,
    which ``valid_polygon`` removes (the area is unchanged)."""
    rounded = Polygon([(round(x, 3), round(y, 3)) for x, y in poly.exterior.coords])
    g = valid_polygon(rounded)
    return [[x, y] for x, y in g.exterior.coords]


def _facet_json(f: Facet) -> dict[str, Any]:
    return {"id": f.id, "plane": [float(v) for v in f.plane], "pitch_rise": round(f.pitch_rise, 2),
            "aspect_deg": round(f.aspect_deg, 1), "roof_type": f.roof_type,
            "plan_area_sqft": round(f.plan_area_sqft, 3), "area_sqft": round(f.area_sqft, 3), "points": f.points,
            "rms_m": round(f.rms_m, 3), "pitch_fit": f.pitch_fit, "pitch_sigma": f.pitch_sigma,
            "supported_pct": f.supported_pct, "polygon": _ring(f.polygon)}


def _edge_json(e: Edge) -> dict[str, Any]:
    out = {"type": e.type, "p0": list(e.p0), "p1": list(e.p1), "length_ft": round(e.length_ft, 2),
           "facets": list(e.facets), "jump_m": e.jump_m}
    if e.type == "level_change":
        out["jump_ft"] = e.jump_ft
    return out


def build_result_json(res: EngineResult, slug: str) -> dict[str, Any]:
    """Assemble the harness dict. A refused result has empty lists and only the quality diagnostics."""
    if res.refused:
        return {"slug": slug, "method": METHOD, "version": VERSION, "roof_outline": [], "facets": [], "edges": [],
                "totals": {}, "diagnostics": {"quality": res.quality.to_dict()}}
    diag = dict(res.diagnostics)
    diag["quality"] = res.quality.to_dict()
    outline = res.outline.drawn if res.outline is not None else None
    return {"slug": slug, "method": METHOD, "version": VERSION,
            "roof_outline": _ring(outline) if outline is not None else [],
            "facets": [_facet_json(f) for f in res.facets], "edges": [_edge_json(e) for e in res.edges],
            "totals": res.totals, "diagnostics": diag}
