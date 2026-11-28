"""The totals of a roof, computed ONCE from the drawn facets and typed edges.

``roof_totals`` is the only place an area, a length by type, a perimeter or a ridge-cap length is added up. The engine
(``finish.facets_stage``) calls it on its facets and edges; the model adapter calls it on the facets and edges it
writes into the model (the same function, so the model's totals and the envelope's totals cannot disagree). Rows are
read by attribute: ``id``, ``area_sqft``, ``roof_type``, ``pitch_rise`` for a facet and ``type``, ``length_ft``,
``facets``, ``high_edge`` for an edge, which both ``types.Facet`` / ``types.Edge`` and the adapter's rows have.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..model import UNPRICED_EDGE_TYPES, predominant_pitch
from .edges import M2F
from .facets import SQM2SQFT
from .params import EngineParams

LENGTH_TYPES = ("eave", "rake", "ridge", "hip", "valley", "level_change", "flat_edge", "transition")
OUTER_TYPES = ("eave", "rake", "flat_edge")  # the outer roof edge: an edge of one of these types with one facet


def roof_totals(facets: Sequence[Any], edges: Sequence[Any], borderline_ids: set[str], p: EngineParams) -> dict[str, Any]:
    """Every total of the roof formed by ``facets`` and ``edges`` (areas in square feet, lengths in feet).

    Areas are the sloped (surface) areas of the facets; ``roofing_pitched_sqft`` and ``roofing_flat_sqft`` split them at
    the flat cut (``roof_type``) and are rounded first, the area is their sum. Some keys are twins of one number
    (``planes_surface_area_sqft``, ``area_sqft_roof_edge``, ``area_sqft_measured_edge``, ``pitched_area_sqft``...): they
    stay for readers of the older contracts until the 0.6.0 key list.
    """
    ap = sum(f.area_sqft for f in facets if f.roof_type != "flat")
    af = sum(f.area_sqft for f in facets if f.roof_type == "flat")
    pitched, flat = round(ap, 1), round(af, 1)
    area = round(pitched + flat, 1)
    lengths = {k: 0.0 for k in LENGTH_TYPES}
    for e in edges:
        if e.type not in UNPRICED_EDGE_TYPES:
            lengths[e.type] = lengths.get(e.type, 0.0) + e.length_ft
    outer = [e for e in edges if len(e.facets) == 1]
    perimeter = round(sum(e.length_ft for e in outer if e.type in OUTER_TYPES), 1)
    flat_ids = {f.id for f in facets if f.roof_type == "flat"}  # a crease between two low-slope facets takes no ridge cap
    ridge_hip = round(sum(e.length_ft for e in edges if e.type in ("ridge", "hip")
                          and not (len(e.facets) == 2 and set(e.facets) <= flat_ids)), 1)
    hv = sum(e.length_ft for e in edges if e.type in ("hip", "valley"))
    squares_surface = (ap + af) / 100.0
    hvq = hv / squares_surface if squares_surface > 0 else 0.0
    cut_up = len(facets) >= p.cut_up_facets or hvq >= p.cut_up_hv_per_sq
    pitch, pitch_area = predominant_pitch([{"kind": "sloped", "pitch_rise": f.pitch_rise, "area_sqft": f.area_sqft}
                                           for f in facets])
    pitch_w = sum(f.area_sqft * f.pitch_rise for f in facets if f.roof_type != "flat")
    return {
        "area_sqft": area, "squares": round(area / 100.0, 3), "facet_count": len(facets),
        "pitched_area_sqft": pitched, "flat_area_sqft": flat,
        "predominant_pitch": pitch, "predominant_pitch_area_sqft": round(pitch_area, 1),
        "lengths_ft": {k: round(v, 2) for k, v in lengths.items()},
        "planes_surface_area_sqft": area, "planes_pitch_weighted": round(pitch_w / ap, 2) if ap > 0 else 0.0,
        "outline_perimeter_ft": perimeter, "ridge_cap_ridge_hip_ft": ridge_hip,
        "high_edge_ft": round(sum(e.length_ft for e in outer if e.high_edge), 1),  # level high sides: rake metal, no cap
        "roofing_pitched_sqft": pitched, "roofing_flat_sqft": flat,
        "roofing_pitched_squares": round(pitched / 100, 2), "roofing_flat_squares": round(flat / 100, 2),
        "low_slope_confirm_sqft": round(sum(f.area_sqft for f in facets if f.id in borderline_ids), 1),
        "flat_edge_ft": round(lengths["flat_edge"], 1), "level_change_ft": round(lengths["level_change"], 1),
        "area_sqft_roof_edge": area, "area_sqft_measured_edge": area, "squares_measured_edge": round(area / 100.0, 3),
        "perimeter_measured_edge_ft": perimeter,
        "complexity": {"facets": len(facets), "hip_valley_ft_per_square": round(hvq, 2),
                       "hint": "cut_up" if cut_up else "simple"}}


def footprint_totals(facets: Iterable[Any], outline: Polygon, wall: Polygon, overhang_applied_m: Iterable[float | None]
                     ) -> dict[str, Any]:
    """The totals that need the county wall line or the outline polygon (metres in, feet and square feet out):
    the area and perimeter of the drawn facets cut to the wall line, the median overhang, the outline's perimeter."""
    clipped = []
    wall_area = 0.0
    for f in facets:
        c = f.polygon.intersection(wall)
        clipped.append(c)
        wall_area += c.area * SQM2SQFT * math.sqrt(1 + (f.pitch_rise / 12.0) ** 2)
    u = unary_union(clipped) if clipped else None
    oh = [v for v in overhang_applied_m if v is not None]
    return {"area_sqft_wall_line": round(wall_area, 1), "squares_wall_line": round(round(wall_area, 1) / 100.0, 1),
            "outline_perimeter_wall_ft": round(u.length * M2F, 1) if u is not None and not u.is_empty else None,
            "overhang_ft_median": round(float(np.median(oh)) * M2F, 2) if oh else None,
            "roof_edge_perimeter_geom_ft": round(outline.length * M2F, 1)}
