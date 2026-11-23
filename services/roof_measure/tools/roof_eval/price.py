"""Price delta: run unit-price rules on (squares, pitch, perimeter, ridge+hip) from the engine and from truth.

The rules file is data passed in by the caller (``price_rules.example.json`` is a clearly fake sample)::

    per_square {pitched, flat}   dollars per square of material, before waste and pitch multiplier
    pitch_multiplier [{min_pitch, mult}]   the highest min_pitch not above the roof's pitch applies (pitched squares only)
    drip_edge_per_lf, ridge_cap_per_lf
    waste_pct {simple, cut_up}   chosen by ``cut_up`` {min_facets, min_hip_valley_ft_per_square}

Pitch definitions differ by side: the engine's is the area-weighted pitch of its pitched facets, a truth file's is its
``predominant_pitch``. Near a multiplier row edge (7.0, 10.0) that alone can move the material line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_rules(path: str | Path | None) -> dict[str, Any] | None:
    return json.loads(Path(path).read_text()) if path else None


def _mult(rules: dict[str, Any], pitch: float | None) -> float:
    m = 1.0
    for row in sorted(rules.get("pitch_multiplier") or [], key=lambda r: r["min_pitch"]):
        if pitch is not None and pitch >= row["min_pitch"]:
            m = row["mult"]
    return m


def waste_pct(rules: dict[str, Any], facets: int | None, hip_valley_ft: float | None, squares: float) -> float:
    """Waste percent: the cut_up rate when facets or hip+valley feet per square reach the rule's limits."""
    cu = rules.get("cut_up") or {}
    spq = (hip_valley_ft / squares) if (hip_valley_ft is not None and squares > 0) else 0.0
    cut = (facets is not None and facets >= cu.get("min_facets", 1e9)) or spq >= cu.get("min_hip_valley_ft_per_square", 1e9)
    return float((rules.get("waste_pct") or {}).get("cut_up" if cut else "simple", 0.0))


def sheet(rules: dict[str, Any], *, pitched_squares: float | None, flat_squares: float | None, pitch: float | None,
          perimeter_ft: float | None, ridge_hip_ft: float | None, facets: int | None = None,
          hip_valley_ft: float | None = None) -> dict[str, float | None]:
    """Sheet lines in dollars: material (squares with waste and pitch multiplier), drip edge, ridge cap, total.
    A line is None when its inputs are missing; the total is None unless every line is known."""
    sq = (pitched_squares or 0.0) + (flat_squares or 0.0)
    material = None
    if pitched_squares is not None and (pitch is not None or pitched_squares <= 0):
        pitch = pitch or 0.0  # no pitched squares: the multiplier does not apply, a missing pitch is 0
        w = 1.0 + waste_pct(rules, facets, hip_valley_ft, sq) / 100.0
        material = (pitched_squares * rules["per_square"]["pitched"] * _mult(rules, pitch)
                    + (flat_squares or 0.0) * rules["per_square"]["flat"]) * w
    drip = None if perimeter_ft is None else perimeter_ft * rules["drip_edge_per_lf"]
    cap = None if ridge_hip_ft is None else ridge_hip_ft * rules["ridge_cap_per_lf"]
    lines = {"material": material, "drip_edge": drip, "ridge_cap": cap}
    lines["total"] = sum(lines.values()) if all(v is not None for v in lines.values()) else None
    return lines


def price_delta(rules: dict[str, Any] | None, engine: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any] | None:
    """Per-line and total dollar and percent difference engine minus truth. Inputs are dicts with the ``sheet`` keyword
    arguments. None without rules."""
    if not rules:
        return None
    e, t = sheet(rules, **engine), sheet(rules, **truth)
    out: dict[str, Any] = {}
    for k in ("material", "drip_edge", "ridge_cap", "total"):
        if e[k] is None or t[k] is None:
            out[k] = None
        else:
            out[k] = {"engine": e[k], "truth": t[k], "delta": e[k] - t[k],
                      "pct": 100.0 * (e[k] - t[k]) / t[k] if t[k] else None}
    return out
