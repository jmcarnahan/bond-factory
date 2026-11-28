"""The ``bond.roof_model/0.2`` envelope: totals with the variant keys, the confidence score, warning codes."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

from .model import TOTALS_KEYS
from .version import CONTRACT, PIPELINE_VERSION

# closed contract vocabulary: every code that still has a producer (0.6.0 removed footprint_solar, method_fallback,
# verifier_*, solar_segments_only, agent_failed_fell_back, flat_roof_assumed, model_failed and model_from_planes)
WARNING_CODES = ("footprint_osm", "footprint_lidar_hull", "source_unreachable", "parcel_without_building",
                 "other_buildings_on_parcel", "parcel_street_match", "low_point_density", "low_slope_confirm",
                 "outline_mismatch", "poor_fit", "low_density", "objects_failed", "other")
VERDICTS = ("pass", "adjusted", "fail", "unverified")
DEGRADED_SOURCES = ("lidar_hull",)
_BASE = {"high": 0.9, "medium": 0.7, "low": 0.5}
_CAP = {"osm": 0.85, "lidar_hull": 0.5}
LOW_DENSITY_PTS_M2 = 12.0


def totals_from_model(model: dict[str, Any]) -> dict[str, Any]:
    """The envelope totals: the keys of ``model.totals`` that contract 0.7 lists (the rest are model-only shape keys)."""
    t = model["totals"]
    return {k: t[k] for k in TOTALS_KEYS}


def confidence_score(model: dict[str, Any], footprint_source: str, verdict: str,
                     density_pts_m2: float | None = None) -> float:
    """0..1 score: model confidence, capped by footprint source, then moved by verdict and point density."""
    c = _BASE.get(model.get("confidence", {}).get("overall"), 0.5)
    c = min(c, _CAP.get(footprint_source, 1.0))
    if verdict == "fail":
        c = min(c, 0.3)
    elif verdict == "unverified":
        c = min(c, 0.7)
    elif verdict == "adjusted":
        c -= 0.05
    if density_pts_m2 is not None and density_pts_m2 < LOW_DENSITY_PTS_M2:
        c -= 0.1
    return round(min(1.0, max(0.0, c)), 2)


def cap_verification(verification: dict[str, Any], footprint_source: str) -> dict[str, Any]:
    """A copy with ``pass`` lowered to ``adjusted`` for a degraded footprint (lidar_hull)."""
    out = copy.deepcopy(verification)
    if out.get("verdict") == "pass" and footprint_source in DEGRADED_SOURCES:
        out["verdict"] = "adjusted"
        out.setdefault("notes", []).append(
            f"Verdict lowered from pass: the footprint came from {footprint_source}, not a parcel or map source.")
    return out


def build_envelope(model: dict[str, Any], *, method_used: str, footprint_source: str, verification: dict[str, Any],
                   warnings: list[str], warning_codes: list[str], density_pts_m2: float | None = None,
                   generated_at: str | None = None, assessment: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the 0.2 result. A degraded footprint (lidar_hull) can be at most ``adjusted``.

    ``assessment`` (``quality.assess_engine``) adds ``model.quality`` and ``model.planes``.
    """
    if len(warnings) != len(warning_codes):
        raise ValueError("warnings and warning_codes must have the same length")
    verification = cap_verification(verification, footprint_source)
    verdict = verification.get("verdict", "unverified")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}")
    codes = [c if c in WARNING_CODES else "other" for c in warning_codes]
    totals = totals_from_model(model)
    if assessment:
        model["quality"] = assessment["quality"]
        if "planes" in assessment:  # absent when the assessment failed
            model["planes"] = assessment["planes"]
    return {
        "contract": CONTRACT,
        "pipeline_version": PIPELINE_VERSION,
        "method_used": method_used,
        "footprint_source": footprint_source,
        "generated_at": generated_at or dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "totals": totals,
        "verification": verification,
        "confidence": confidence_score(model, footprint_source, verdict, density_pts_m2),
        "warnings": list(warnings),
        "warning_codes": codes,
    }
