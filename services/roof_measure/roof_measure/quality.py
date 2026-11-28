"""Quality of a plane-engine result: numbers and reason codes, never a label. The consumer decides what is good or rough."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

LEVEL_MIN_SHARE = 0.05  # a facet counts for level_spread_ft when it covers this share of the roof's area


ENGINE_COPIED = ("parcel_street_match", "other_buildings_on_parcel", "not_exact_parcel")  # warning codes passed on as reasons


def engine_quality(res: Any, model: dict[str, Any], warning_codes: Iterable[str] = ()) -> dict[str, Any]:
    """``model.quality`` of an engine result: the contract-0.4 signals, and the older keys with their engine analogues.

    New keys: ``engine``, ``fit_covered``, ``fit_all``, ``coverage``, ``supported_pct``, ``density_pts_m2``,
    ``parcel_match``, ``outline_source``, ``verdict``, ``outline_shift`` and ``reasons``.
    Old keys, so a reader that knows only 0.3 still gets numbers: ``plane_mismatch_pct`` = share of roof points off
    their facet's plane (100 x (1 - fit_covered)), ``outline_covered_pct`` = roof-point support over the outline,
    ``model_uncovered_pct`` = share of roof points outside every facet, ``level_spread_ft``, ``planes_lidar`` (planes
    used) and ``facets_model``.
    """
    q = res.quality
    codes = set(warning_codes)
    facets = model.get("facets", [])
    big = [f for f in facets if f["plan_area_sqft"] >= LEVEL_MIN_SHARE * sum(g["plan_area_sqft"] for g in facets)]
    heights = [sum(f["plane_eq"][0] * x + f["plane_eq"][1] * y + f["plane_eq"][2] for x, y in f["polygon"]) / len(f["polygon"])
               for f in big]

    def pct(v: float | None) -> float | None:
        return None if v is None else round(100.0 * v, 1)

    reasons = [r for r in q.reasons if r != "lidar_too_sparse"]
    if res.totals.get("low_slope_confirm_sqft"):
        reasons.append("low_slope_confirm")
    reasons += [c for c in ENGINE_COPIED if c in codes and c not in reasons]
    return {
        "engine": "planes/1", "engine_params": res.params_hash, "verdict": q.verdict, "fit_covered": q.fit_covered, "fit_all": q.fit_all,
        "fit_clear": q.fit_clear, "tree_cover_pct": q.tree_cover_pct, "coverage": q.coverage, "supported_pct": q.supported_pct, "density_pts_m2": q.density,
        "parcel_match": q.parcel_match, "outline_source": q.outline_source,
        "outline_shift": q.outline_shift, "flat_share": q.flat_share,
        "plane_mismatch_pct": None if q.fit_covered is None else round(100.0 * (1.0 - q.fit_covered), 1),
        "outline_covered_pct": None if q.roof_cover_of_outline is None else round(min(100.0, 100.0 * q.roof_cover_of_outline), 1),
        "model_uncovered_pct": None if q.coverage is None else round(100.0 * (1.0 - q.coverage), 1),
        "level_spread_ft": round(max(heights) - min(heights), 1) if heights else None,
        "planes_lidar": len({f.label for f in res.facets}),
        "facets_model": len(facets), "roof_part_missed_sqft": res.roof_part_missed_sqft, "reasons": reasons}


def assess_engine(res: Any, model: dict[str, Any], warning_codes: Iterable[str] = ()) -> dict[str, Any]:
    """The assessment ``envelope.build_envelope`` takes for an engine result: ``{"quality", "planes"}``."""
    from .engine.adapter import engine_planes

    return {"quality": engine_quality(res, model, warning_codes), "planes": engine_planes(model)}
