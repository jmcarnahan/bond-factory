"""The totals of a roof, computed ONCE from the drawn facets, typed edges and objects.

``roof_totals`` is the only place an area, a length by type or an object count is added up, and it writes exactly the
keys of contract 0.6 (``docs/contract-0.6.md``, a test reads that table). The engine calls it on its facets, edges and
objects (``finish.assemble``); the model adapter calls it on the facets, edges and objects it writes into the model (the
same function, so the model's totals and the envelope's totals cannot disagree). Rows are read by attribute: ``id``,
``area_sqft``, ``roof_type``, ``pitch_rise`` for a facet and ``type``, ``length_ft`` for an edge, which both
``types.Facet`` / ``types.Edge`` and the adapter's rows have; an object is the dict ``objects.find_objects`` returns.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..model import UNPRICED_EDGE_TYPES

LENGTH_TYPES = ("eave", "rake", "ridge", "hip", "valley", "level_change", "step_flashing", "wall_flashing", "flat_edge",
                "transition")
def _perimeter_ft(o: dict[str, Any]) -> float:
    return 2.0 * (o["size_ft"][0] + o["size_ft"][1])


def roof_totals(facets: Sequence[Any], edges: Sequence[Any], borderline_ids: set[str],
                objects: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    """Every total of the roof formed by ``facets``, ``edges`` and ``objects`` (square feet and feet).

    Areas are the sloped (surface) areas of the facets; ``roofing_pitched_sqft`` and ``roofing_flat_sqft`` split them at
    the flat cut (``roof_type``) and are rounded first, the area is their sum. Lengths are the sums of the edges of one
    type (an unpriced ``flat_seam`` is in no total). ``exposed_edge_ft`` adds the two step types and the sides of the
    lanterns; ``eave_rake_ft`` is ``eave + rake + flat_edge + exposed``. Only chimneys and lanterns are counted; an
    ``unknown`` object is counted nowhere.
    """
    ap = sum(f.area_sqft for f in facets if f.roof_type != "flat")
    af = sum(f.area_sqft for f in facets if f.roof_type == "flat")
    pitched, flat = round(ap, 1), round(af, 1)
    area = round(pitched + flat, 1)
    length = {k: 0.0 for k in LENGTH_TYPES}
    for e in edges:
        if e.type not in UNPRICED_EDGE_TYPES:
            length[e.type] += e.length_ft
    chimneys = [o for o in objects if o["kind"] == "chimney"]
    lanterns = [o for o in objects if o["kind"] == "lantern"]
    exposed = length["step_flashing"] + length["wall_flashing"] + sum(_perimeter_ft(o) for o in lanterns)
    pitch_w = sum(f.area_sqft * f.pitch_rise for f in facets if f.roof_type != "flat")

    def r(v: float) -> float:
        return round(v, 2)

    return {
        "area_sqft": area, "squares": round(area / 100.0, 3), "roofing_pitched_sqft": pitched, "roofing_flat_sqft": flat,
        "planes_pitch_weighted": round(pitch_w / ap, 2) if ap > 0 else 0.0, "plane_count": len(facets),
        "eave_ft": r(length["eave"]), "rake_ft": r(length["rake"]), "flat_edge_ft": r(length["flat_edge"]),
        "exposed_edge_ft": r(exposed),
        "eave_rake_ft": r(length["eave"] + length["rake"] + length["flat_edge"] + exposed),
        "ridge_ft": r(length["ridge"]), "hip_ft": r(length["hip"]), "valley_ft": r(length["valley"]),
        "ridge_hip_ft": r(length["ridge"] + length["hip"]),
        "step_flashing_ft": r(length["step_flashing"]), "wall_flashing_ft": r(length["wall_flashing"]),
        "transition_ft": r(length["transition"]), "level_change_ft": r(length["level_change"]),
        "chimney_count": len(chimneys), "chimney_perimeter_ft": r(sum(_perimeter_ft(o) for o in chimneys)),
        "lantern_count": len(lanterns),
        # kept for ONE release: phone builds in the field recognise an engine roof by the presence of this key
        "area_sqft_roof_edge": area,
        "low_slope_confirm_sqft": round(sum(f.area_sqft for f in facets if f.id in borderline_ids), 1)}
