"""Envelope warnings and their codes, collected from the footprint, the model, the verifier and the method."""

from __future__ import annotations

from typing import Any

LOW_DENSITY_WARN_PTS_M2 = 8.0  # warn below this; the envelope confidence also drops 0.1 below 12

VERIFIER_NOTES = {
    "adjusted": ("verifier_adjusted", "The verifier merged nearly collinear segments and recomputed the totals."),
    "fail": ("verifier_failed", "The verifier found the measurement inconsistent: a total moved more than allowed."),
    "unverified": ("verifier_unverified", "The measurement was not checked by the LLM verifier."),
}


def collect_warnings(model: dict[str, Any], fpinfo: dict[str, Any], verification: dict[str, Any],
                     density: float | None, fallback_from: str | None, method: str,
                     extra: list[tuple[str, str]] | None = None) -> tuple[list[str], list[str]]:
    """(warnings, warning_codes) of equal length: footprint, parcel, density, method, model, verifier."""
    pairs: list[tuple[str, str]] = list(zip(fpinfo["codes"], fpinfo["warnings"], strict=True))
    if fpinfo.get("other_buildings"):
        n = fpinfo["other_buildings"]
        text = f"{n} other building outline(s) lie on the same parcel; only the largest was measured."
        pairs.append(("other_buildings_on_parcel", text))
    if density is not None and density < LOW_DENSITY_WARN_PTS_M2:
        pairs.append(("low_point_density", f"LiDAR density is low ({density:.1f} points/m2, under {LOW_DENSITY_WARN_PTS_M2:.0f}); edges and pitch may be rough."))
    if fallback_from:
        pairs.append(("method_fallback", f"LiDAR was unavailable or too sparse; used {method} instead."))
    if method == "solar_agent":
        pairs.append(("solar_segments_only", "Geometry comes from Google Solar roof segments, not LiDAR."))
    pairs += [("other", w) for w in model.get("warnings", [])]
    pairs += list(extra or [])
    verdict = verification.get("verdict", "unverified")
    if verdict in VERIFIER_NOTES:
        pairs.append(VERIFIER_NOTES[verdict])
    seen: set[tuple[str, str]] = set()
    unique = [p for p in pairs if not (p in seen or seen.add(p))]
    return [t for _, t in unique], [c for c, _ in unique]
