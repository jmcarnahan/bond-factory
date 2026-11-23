"""Priced vs drawn numbers. An engine may DRAW facets at the measured roof edge but PRICE at an overhang scale, and says so
in its totals. Comparisons with truth (squares, perimeter, ridge+hip, pitch, price delta) read the priced totals keys when
present and fall back to geometry-derived values when absent; shape metrics always use the drawn geometry.

Keys read: planes_surface_area_sqft (area), planes_pitch_weighted, outline_perimeter_ft, ridge_cap_ridge_hip_ft, and for the
split roofing_pitched_squares / roofing_flat_squares; for the consistency check area_sqft_wall_line, area_sqft_roof_edge,
outline_perimeter_wall_ft.
"""

from __future__ import annotations

import math
from typing import Any

from . import m_shape
from .geom import Roof

KEYS = {"area_sqft": "planes_surface_area_sqft", "pitch": "planes_pitch_weighted", "perimeter_ft": "outline_perimeter_ft",
        "ridge_hip_ft": "ridge_cap_ridge_hip_ft"}
TOL = 0.01  # relative slack of the consistency checks
EDGE_TOL = 0.02


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(x) else None


def priced(roof: Roof) -> dict[str, Any]:
    """The priced numbers of a result: each value from the totals key when present, else from the drawn geometry;
    ``src`` names the source per value ("totals" | "geometry")."""
    fp, ln = m_shape.flat_pitched(roof), m_shape.lengths(roof)
    drawn = {"area_sqft": fp["area_sqft"], "pitch": fp["pitch_weighted"], "perimeter_ft": ln["perimeter"],
             "ridge_hip_ft": ln["ridge_hip"]}
    out: dict[str, Any] = {"src": {}}
    for k, key in KEYS.items():
        v = _num(roof.declared.get(key))
        out[k], out["src"][k] = (v, "totals") if v is not None else (drawn[k], "geometry")
    out["squares"] = out["area_sqft"] / 100.0
    ps, fs = _num(roof.declared.get("roofing_pitched_squares")), _num(roof.declared.get("roofing_flat_squares"))
    if ps is not None and fs is not None:
        out["pitched_squares"], out["flat_squares"] = ps, fs
    else:  # the drawn pitched / flat shares applied to the priced area
        share = fp["pitched_sqft"] / fp["area_sqft"] if fp["area_sqft"] else 0.0
        out["pitched_squares"], out["flat_squares"] = out["squares"] * share, out["squares"] * (1 - share)
    return out


def consistency(roof: Roof, p: dict[str, Any]) -> dict[str, Any]:
    """An engine cannot report arbitrary totals: the priced area must lie between the wall-line area and the drawn area, the
    priced perimeter between the wall perimeter and the drawn perimeter, and a declared roof-edge area must match the drawn
    area. ``ok`` is None when the totals carry nothing to check (no priced keys)."""
    d = roof.declared
    fp, ln = m_shape.flat_pitched(roof), m_shape.lengths(roof)
    why: list[str] = []
    checked = False

    def between(name: str, val: float, wall: float | None, drawn: float) -> None:
        nonlocal checked
        if wall is None:
            return
        checked = True
        lo, hi = min(wall, drawn), max(wall, drawn)
        if not (lo * (1 - TOL) <= val <= hi * (1 + TOL)):
            why.append(f"{name} {val:.0f} outside [{lo:.0f}, {hi:.0f}]")

    if p["src"]["area_sqft"] == "totals":
        between("priced area", p["area_sqft"], _num(d.get("area_sqft_wall_line")), fp["area_sqft"])
    if p["src"]["perimeter_ft"] == "totals":
        between("priced perimeter", p["perimeter_ft"], _num(d.get("outline_perimeter_wall_ft")), ln["perimeter"])
    edge = _num(d.get("area_sqft_roof_edge"))
    if edge is not None:
        checked = True
        if abs(edge - fp["area_sqft"]) > EDGE_TOL * fp["area_sqft"]:
            why.append(f"declared roof-edge area {edge:.0f} differs from drawn {fp['area_sqft']:.0f}")
    return {"ok": (not why) if checked else None, "why": why}
