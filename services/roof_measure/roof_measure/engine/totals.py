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

from ..model import SCHEMA_ONLY_EDGE_TYPES, UNPRICED_EDGE_TYPES

LENGTH_TYPES = ("eave", "rake", "ridge", "hip", "valley", "level_change", "step_flashing", "wall_flashing", "flat_edge",
                "transition")
def _perimeter_ft(o: dict[str, Any]) -> float:
    return 2.0 * (o["size_ft"][0] + o["size_ft"][1])


def roof_totals(facets: Sequence[Any], edges: Sequence[Any], borderline_ids: set[str],
                objects: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
    """Every total of the roof formed by ``facets``, ``edges`` and ``objects`` (square feet and feet).

    Areas are the sloped (surface) areas of the facets; ``roofing_pitched_sqft`` and ``roofing_flat_sqft`` split them at
    the flat cut (``roof_type``) and are rounded first, the area is their sum. Lengths are the sums of the edges of one
    type (an unpriced ``flat_seam`` is in no total, nor are ``parapet`` and ``unspecified``: the engine never emits them, but a
    stored or hand-built model may carry them and ``model.totals.lengths_ft`` counts them under their own type). ``exposed_edge_ft`` adds the two step types and the sides of the
    lanterns; ``eave_rake_ft`` is ``eave + rake + flat_edge + exposed``. Only chimneys and lanterns are counted; an
    ``unknown`` object is counted nowhere.
    """
    ap = sum(f.area_sqft for f in facets if f.roof_type != "flat")
    af = sum(f.area_sqft for f in facets if f.roof_type == "flat")
    pitched, flat = round(ap, 1), round(af, 1)
    area = round(pitched + flat, 1)
    length = {k: 0.0 for k in LENGTH_TYPES}
    for e in edges:
        if e.type not in UNPRICED_EDGE_TYPES and e.type not in SCHEMA_ONLY_EDGE_TYPES:  # in no contract total
            length[e.type] += e.length_ft
    chimneys = [o for o in objects if o["kind"] == "chimney"]
    lanterns = [o for o in objects if o["kind"] == "lantern"]
    pitch_w = sum(f.area_sqft * f.pitch_rise for f in facets if f.roof_type != "flat")

    def r(v: float) -> float:
        return round(v, 2)

    # composites are sums of the ROUNDED parts: anyone adding the published values gets the published total, exactly
    parts = {k: r(v) for k, v in length.items()}
    exposed = r(parts["step_flashing"] + parts["wall_flashing"] + r(sum(_perimeter_ft(o) for o in lanterns)))
    return {
        "area_sqft": area, "squares": round(area / 100.0, 3), "roofing_pitched_sqft": pitched, "roofing_flat_sqft": flat,
        "planes_pitch_weighted": round(pitch_w / ap, 2) if ap > 0 else 0.0, "plane_count": len(facets),
        "eave_ft": parts["eave"], "rake_ft": parts["rake"], "flat_edge_ft": parts["flat_edge"],
        "exposed_edge_ft": exposed,
        "eave_rake_ft": r(parts["eave"] + parts["rake"] + parts["flat_edge"] + exposed),
        "ridge_ft": parts["ridge"], "hip_ft": parts["hip"], "valley_ft": parts["valley"],
        "ridge_hip_ft": r(parts["ridge"] + parts["hip"]),
        "step_flashing_ft": parts["step_flashing"], "wall_flashing_ft": parts["wall_flashing"],
        "transition_ft": parts["transition"], "level_change_ft": parts["level_change"],
        "chimney_count": len(chimneys), "chimney_perimeter_ft": r(sum(_perimeter_ft(o) for o in chimneys)),
        "lantern_count": len(lanterns),
        # kept for ONE release: phone builds in the field recognise an engine roof by the presence of this key
        "area_sqft_roof_edge": area,
        "low_slope_confirm_sqft": round(sum(f.area_sqft for f in facets if f.id in borderline_ids), 1)}
