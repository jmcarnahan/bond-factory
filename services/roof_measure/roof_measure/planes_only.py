"""The safety net: a roof result from the LiDAR planes alone when the simple roof model cannot be built.

When the block model fails validation (``ModelError``) or its geometry cannot be built, but LiDAR planes were found
and snapped (``planes.snap_with_stats``), the measurement still answers: ``model.facets``, ``model.blocks`` and
``model.edges`` are empty, ``model.source.planes_only`` is true, ``model.quality`` carries ``model_failed`` and the
plane totals feed the envelope totals. The edge totals (``eave_ft``, ``rake_ft``, ``ridge_ft`` ...) are NOT measured
in this case: only the outline perimeter is known, so it stands in for the eaves and the rest are 0.0.
"""

from __future__ import annotations

import logging
from typing import Any

from .classify import BlockSet
from .model import ModelError, build_model, pitch_bucket
from .planes import snap_with_stats

log = logging.getLogger("roof_measure.planes_only")

CODE = "model_failed"
WARNING = "A simple roof diagram could not be built; the measured roof planes are returned instead."
NOT_VERIFIED = "The roof diagram could not be built, so there were no edges to verify."
DROPPED_REASONS = ("multi_plane_simplified", "model_misses_roof_area")  # the model_failed reason says it already


def has_planes(base: BlockSet, warning_codes: list[str]) -> bool:
    """True when at least one LiDAR plane survives snapping (the condition for the safety net)."""
    if not base.blocks:
        return False
    snap = snap_with_stats(base, clip_to_footprint="parcel_street_match" not in warning_codes)
    return not snap.failed and bool(snap.planes)


def build_planes_only_model(base: BlockSet, source: dict[str, Any], cause: str) -> dict[str, Any]:
    """A valid model without blocks, facets or edges; confidence is fixed low (nothing was modelled)."""
    model = build_model(base, [], {**source, "planes_only": True}, None)
    model["confidence"] = {"overall": "low", "notes": [
        "The simple roof diagram could not be built; this result is the measured roof planes only.", cause]}
    return model


def planes_only_quality(quality: dict[str, Any]) -> dict[str, Any]:
    """``quality`` of a planes-only model: mismatch unknown, ``model_failed`` first, the rest of the reasons kept."""
    out = dict(quality)
    out["plane_mismatch_pct"] = None
    out["reasons"] = [CODE, *[r for r in quality.get("reasons", []) if r not in DROPPED_REASONS and r != CODE]]
    return out


def planes_only_totals(plane_totals: dict[str, Any]) -> dict[str, Any]:
    """Every 0.2 totals key, from the planes: area, squares and pitch from the planes, the outline perimeter for the
    eaves and drip edges, 0.0 for the edges nobody measured, ``facets`` 0, plus the four plane totals."""
    area = float(plane_totals.get("planes_surface_area_sqft", 0.0))
    perimeter = float(plane_totals.get("outline_perimeter_ft", 0.0))
    pitch = float(plane_totals.get("planes_pitch_weighted", 0.0))
    out: dict[str, Any] = {
        "area_sqft": area, "squares": area / 100.0, "eave_ft": perimeter, "rake_ft": 0.0, "ridge_ft": 0.0,
        "hip_ft": 0.0, "valley_ft": 0.0, "step_flashing_ft": 0.0,
        "predominant_pitch": pitch_bucket("sloped", pitch), "facets": 0,
        "drip_edge_eave_ft": perimeter, "drip_edge_eave_rake_ft": perimeter,
        "ridge_cap_ridge_ft": 0.0, "ridge_cap_ridge_hip_ft": 0.0}
    out = {k: (v if k == "facets" else round(float(v), 3)) for k, v in out.items()}
    return out | plane_totals


def need_roof_blocks(roof_blocks: list[Any], base: BlockSet, fpinfo: dict[str, Any]) -> None:
    """No roof block came out of the classification although LiDAR planes exist: that is a model failure too.

    (Without planes an empty roof stays what it was: a result with no area.)
    """
    if not roof_blocks and has_planes(base, fpinfo["codes"]):
        raise ModelError("no roof block survived the classification")


def model_or_raise(exc: BaseException, base: BlockSet, source: dict[str, Any], fpinfo: dict[str, Any],
                   cause: str) -> dict[str, Any]:
    """The planes-only model, or ``exc`` raised again when no LiDAR plane exists (the error stays what it was)."""
    if not has_planes(base, fpinfo["codes"]):
        raise exc
    log.warning("simple roof model failed (%s); returning the planes only", type(exc).__name__)
    return build_planes_only_model(base, source, cause)


def assessment_or_raise(assessment: dict[str, Any] | None, exc: BaseException) -> dict[str, Any]:
    """The assessment of a planes-only result; ``exc`` raised again when the planes did not come out."""
    if not assessment or not assessment.get("planes") or not assessment.get("totals"):
        raise exc
    return {**assessment, "quality": planes_only_quality(assessment["quality"])}
