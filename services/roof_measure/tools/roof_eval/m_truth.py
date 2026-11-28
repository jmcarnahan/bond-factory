"""Comparison of one result with one truth file (plan 3.5 schema v2), tier merging, and the T3 aggregate."""

from __future__ import annotations

from typing import Any

from . import m_shape, price, stats
from .geom import Roof


def drawn_basis(roof: Roof) -> dict[str, Any]:
    """The numbers of the one roof (the drawn facets and the recomputed edges): the only basis since 0.6.0."""
    fp, ln = m_shape.flat_pitched(roof), m_shape.lengths(roof)
    return {"area_sqft": fp["area_sqft"], "squares": fp["squares"], "pitch": fp["pitch_weighted"], "perimeter_ft": ln["perimeter"],
            "ridge_hip_ft": ln["ridge_hip"]}


LENGTH_KEYS = ("eave", "rake", "ridge", "hip", "valley", "step_flashing", "level_change")
T3_MIN_CONFIDENCE = ("medium", "high")


def pct(a: float | None, b: float | None) -> float | None:
    """100 * (a - b) / b; None when either is missing or b is 0."""
    if a is None or b in (None, 0):
        return None
    return 100.0 * (a - b) / b


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _truth_flat_edge(t: dict[str, Any]) -> float:
    """flat_edge feet of a truth file: lengths_ft.flat_edge, else lengths_ft_extra.flat_edge, else 0."""
    return _num((t.get("lengths_ft") or {}).get("flat_edge")) or _num((t.get("lengths_ft_extra") or {}).get("flat_edge")) or 0.0


def truth_inputs(t: dict[str, Any]) -> dict[str, Any]:
    """The price-sheet inputs a truth file supports (None where it is silent)."""
    ln = t.get("lengths_ft") or {}
    sq = _num(t.get("squares"))
    if sq is None and _num(t.get("area_sqft")) is not None:
        sq = t["area_sqft"] / 100.0
    flat = _num(t.get("flat_area_sqft"))
    flat_sq = flat / 100.0 if flat is not None else 0.0
    eave, rake, flat_edge = _num(ln.get("eave")), _num(ln.get("rake")), _truth_flat_edge(t)
    ridge, hip, valley = _num(ln.get("ridge")), _num(ln.get("hip")), _num(ln.get("valley"))
    return {"pitched_squares": None if sq is None else max(0.0, sq - flat_sq), "flat_squares": flat_sq,
            "pitch": _num(t.get("predominant_pitch")),
            "perimeter_ft": eave + rake + flat_edge if eave is not None and rake is not None else None,
            "ridge_hip_ft": ridge + hip if ridge is not None and hip is not None else None,
            "facets": t.get("facet_count") or (len(t["facets"]) if t.get("facets") else None),
            "hip_valley_ft": hip + valley if hip is not None and valley is not None else None}


def engine_inputs(roof: Roof) -> dict[str, Any]:
    """Price-sheet inputs of a result, from the drawn roof."""
    fp, ln = m_shape.flat_pitched(roof), m_shape.lengths(roof)
    return {"pitched_squares": fp["pitched_sqft"] / 100.0, "flat_squares": fp["flat_sqft"] / 100.0, "pitch": fp["pitch_weighted"],
            "perimeter_ft": ln["perimeter"], "ridge_hip_ft": ln["ridge_hip"], "facets": len(roof.facets),
            "hip_valley_ft": ln["hip"] + ln["valley"]}


def compare(roof: Roof, t: dict[str, Any], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Metrics of ``roof`` against one truth file; every field is omitted or None when the truth is silent on it."""
    fp, ln = m_shape.flat_pitched(roof), m_shape.lengths(roof)
    pr = drawn_basis(roof)  # one roof, one area: every tier is compared with the drawn roof
    o: dict[str, Any] = {"source": t.get("source"), "tier": t.get("tier"), "confidence": t.get("confidence")}
    tsq = _num(t.get("squares"))
    if tsq is None and _num(t.get("area_sqft")) is not None:
        tsq = t["area_sqft"] / 100.0
    o["squares"] = {"truth": tsq, "result": pr["squares"], "err_pct": pct(pr["squares"], tsq),
                    "ratio": pr["squares"] / tsq if tsq else None}
    for k, rv in (("flat_area_sqft", fp["flat_sqft"]), ("pitched_area_sqft", fp["pitched_sqft"])):
        if _num(t.get(k)) is not None:
            o[k] = {"truth": t[k], "result": rv, "err_pct": pct(rv, t[k]), "abs_diff": rv - t[k]}
    if _num(t.get("predominant_pitch")) is not None and pr["pitch"] is not None:
        o["pitch"] = {"truth": t["predominant_pitch"], "result": pr["pitch"], "abs_diff": abs(pr["pitch"] - t["predominant_pitch"])}
    if _num(t.get("facet_count")) is not None:
        o["facet_count"] = {"truth": t["facet_count"], "result": len(roof.facets),
                            "abs_diff": abs(len(roof.facets) - t["facet_count"])}
    tl = t.get("lengths_ft") or {}
    lens = {}
    for k in LENGTH_KEYS:
        if _num(tl.get(k)) is not None:
            lens[k] = {"truth": tl[k], "result": ln[k], "err_pct": pct(ln[k], tl[k]), "abs_diff": ln[k] - tl[k]}
    if _num(tl.get("eave")) is not None and _num(tl.get("rake")) is not None:
        tp = tl["eave"] + tl["rake"] + _truth_flat_edge(t)
        lens["perimeter"] = {"truth": tp, "result": pr["perimeter_ft"], "err_pct": pct(pr["perimeter_ft"], tp),
                             "abs_diff": pr["perimeter_ft"] - tp}
    if _num(tl.get("ridge")) is not None and _num(tl.get("hip")) is not None:
        th = tl["ridge"] + tl["hip"]
        lens["ridge_hip"] = {"truth": th, "result": pr["ridge_hip_ft"], "err_pct": pct(pr["ridge_hip_ft"], th),
                             "abs_diff": pr["ridge_hip_ft"] - th}
    if lens:
        o["lengths"] = lens
    if t.get("facets"):
        o["facet_iou"] = m_shape.facet_iou(roof, t["facets"])
        o["flat_pitched_agreement"] = m_shape.flat_pitched_agreement(roof, t["facets"])
    pd = price.price_delta(rules, engine_inputs(roof), truth_inputs(t))
    if pd is not None:
        o["price"] = pd
    return o


def flatten(d: dict[str, Any], prefix: str = "") -> dict[str, float]:
    """Numeric leaves of a nested dict, keyed ``a.b.c``."""
    out: dict[str, float] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        elif _num(v) is not None:
            out[f"{prefix}{k}"] = float(v)
    return out


def merge_tier(items: list[dict[str, Any]]) -> dict[str, float]:
    """One flat dict per tier per house: the mean of every numeric leaf over the tier's truth files
    (two label runs of one house average; the number of files is kept as ``n_files``)."""
    flats = [flatten(i) for i in items]
    keys = sorted({k for f in flats for k in f})
    out = {k: sum(f[k] for f in flats if k in f) / sum(1 for f in flats if k in f) for k in keys}
    out["n_files"] = float(len(items))
    return out


def t2_confidence(files: list[dict[str, Any]]) -> str | None:
    """The label confidence of a house's T2 truth: ``medium`` if any T2 file says medium, ``high`` if all valued files say
    high, None when no T2 file carries a confidence of high or medium (older labels): such houses count in "all" only."""
    cs = [f.get("confidence") for f in files if f.get("tier") == "T2" and f.get("confidence") in ("high", "medium")]
    if not cs:
        return None
    return "medium" if "medium" in cs else "high"


def t3_aggregate(rows: list[dict[str, Any]], key: str = "ratio") -> dict[str, Any] | None:
    """The T3 aggregate over per-house records (``key`` the per-file ratio, result over contractor squares): median of result/contractor squares with a bootstrap 90% interval.
    Only T3 files whose confidence is medium or high count, one ratio per house; never a per-house verdict."""
    ratios = []
    for r in rows:  # one ratio per house: the mean over its T3 files
        xs = [(t.get("squares") or {}).get(key) for t in (r.get("truth_files") or [])
              if t.get("tier") == "T3" and t.get("confidence") in T3_MIN_CONFIDENCE]
        xs = [x for x in xs if x is not None]
        if xs:
            ratios.append(sum(xs) / len(xs))
    ci = stats.bootstrap_median_ci(ratios, 0.90)
    if ci is None:
        return None
    iqr = stats.percentile(ratios, 75) - stats.percentile(ratios, 25)
    return {"n": len(ratios), "median_ratio": ci[0], "lo90": ci[1], "hi90": ci[2], "iqr": iqr}
