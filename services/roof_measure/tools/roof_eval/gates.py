"""Gates as data. A gates.json holds thresholds the director supplies; this module only evaluates them.

    {"compare": {"area_pct": 3, "facets": 2, "fit_all_drop": 0.05, "flag_share": 0.05, "median_area_pct": 1},
     "gates": [{"name": "fit_covered share", "metric": "fit_covered", "agg": "share", "pred": {"op": ">=", "value": 0.8},
                "where": ["roof_class=pitched"], "require": ["automation_ok"], "op": ">=", "value": 0.7, "min_n": 10}]}

``metric``: a per-house flag (automation, automation_ok), a truth-free metric of ``m`` (fit_all, facets, ...) or a dotted
truth path (``truth.T2.facet_iou.mean_iou``). ``agg``: rate (share of houses where the flag is true), share (share of
houses whose value satisfies ``pred`` {op, value}, op also ``between`` with a [lo, hi] value; a missing value fails it
unless ``valued_only``), median, mean, p90, min, max, sum, count, ratio (pooled sum of ``metric`` over sum of
``denominator``), t3_contains (the 90% interval of the T3 median ratio contains ``target``, default 1.0) and t3_iqr_ratio
(T3 ratio IQR over the IQR of ``baseline``'s).
``where``: manifest filters (``key=a,b`` / ``key!=a``); ``require``: flags that must be true for a house to count.
``min_n`` counts the houses of the population that have a numeric value for the metric (``n_value``; ``n`` is the whole
population). Fewer than ``min_n`` fails the gate unless ``"on_insufficient": "skip"``.
"""

from __future__ import annotations

import operator
from typing import Any

from . import data, m_truth, stats

OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}
FLAGS = ("automation", "automation_ok", "invalid_or_crashed")


def _dig(d: Any, parts: list[str]) -> Any:
    """Look ``parts`` up in nested dicts; a dict may also hold dotted keys (the flattened truth tiers)."""
    if not parts:
        return d
    if not isinstance(d, dict):
        return None
    for n in range(len(parts), 0, -1):
        k = ".".join(parts[:n])
        if k in d:
            return _dig(d[k], parts[n:])
    return None


def metric(rec: dict[str, Any], path: str) -> Any:
    """A metric of a per-house record by name (see the module doc)."""
    if path in FLAGS or path in ("status", "verdict", "runtime_s"):
        return rec.get(path)
    if path == "verdict_ok":
        return rec.get("verdict") == "ok"
    if path.startswith("truth."):
        return _dig(rec.get("truth"), path.split(".")[1:])
    return _dig(rec.get("m"), path.split("."))


def _in_population(rec: dict[str, Any], g: dict[str, Any]) -> bool:
    row = {**rec.get("row", {}), "id": rec["id"]}
    return data.matches(row, data.parse_where(g.get("where"))) and all(bool(metric(rec, k)) for k in g.get("require", []))


def _holds(v: Any, pred: dict[str, Any]) -> bool:
    if v is None or isinstance(v, bool):
        return False
    if pred["op"] == "between":
        return pred["value"][0] <= v <= pred["value"][1]
    return OPS[pred["op"]](v, pred["value"])


def aggregate(vals: list[Any], agg: str, pred: dict[str, Any] | None = None, valued_only: bool = False) -> float | None:
    """One number from per-house values (None = missing). ``share`` counts a missing value as failing unless
    ``valued_only`` (then the share is over the houses that have a value)."""
    if agg == "count":
        return float(len(vals))
    if agg == "rate":
        return sum(1 for v in vals if v) / len(vals) if vals else None
    if agg == "share":
        pool = [v for v in vals if v is not None] if valued_only else vals
        return sum(1 for v in pool if _holds(v, pred or {})) / len(pool) if pool else None
    nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
    fn = {"median": stats.median, "mean": stats.mean, "p90": lambda x: stats.percentile(x, 90),
          "min": lambda x: min(x) if x else None, "max": lambda x: max(x) if x else None,
          "sum": lambda x: float(sum(x))}[agg]
    return fn(nums)


def _t3_gate(g: dict[str, Any], pop: list[dict[str, Any]], baseline_t3) -> tuple[float | None, int]:
    t3 = m_truth.t3_aggregate(pop)
    if t3 is None:
        return None, 0
    if g["agg"] == "t3_contains":  # 1.0 when the 90% interval of the median ratio contains the target
        return float(t3["lo90"] <= g.get("target", 1.0) <= t3["hi90"]), t3["n"]
    base = baseline_t3(g["baseline"]) if baseline_t3 else None
    if not base or not base.get("iqr"):
        return None, t3["n"]
    return t3["iqr"] / base["iqr"], t3["n"]


def _value(g: dict[str, Any], pop: list[dict[str, Any]], baseline_t3) -> tuple[float | None, int]:
    """(gate value, number of houses that have the metric) for one gate over its population."""
    if g["agg"] in ("t3_contains", "t3_iqr_ratio"):
        return _t3_gate(g, pop, baseline_t3)
    vals = [metric(r, g["metric"]) for r in pop]
    if g["agg"] == "ratio":  # pooled: sum(metric) / sum(denominator)
        den = sum(metric(r, g["denominator"]) or 0.0 for r in pop)
        return (sum(v or 0.0 for v in vals) / den if den else None), sum(1 for r in pop if metric(r, g["denominator"]))
    nv = len(pop) if g["agg"] in ("rate", "count") else sum(1 for x in vals if isinstance(x, (int, float)) and not isinstance(x, bool))
    return None, nv  # the value itself is computed after the min_n check


def evaluate(spec: dict[str, Any], recs: list[dict[str, Any]], baseline_t3=None) -> list[dict[str, Any]]:
    """One result per gate: name, value, op, threshold, n, n_value, passed, note. ``baseline_t3(name)`` returns a frozen
    baseline's T3 aggregate (for the IQR gate)."""
    out = []
    recs = [r for r in recs if not data.is_canary(r.get("row", {}))]  # canaries are never evidence (own section in tables.md)
    for g in spec.get("gates", []):
        pop = [r for r in recs if _in_population(r, g)]
        v, nv = _value(g, pop, baseline_t3)
        res = {"name": g["name"], "n": len(pop), "n_value": nv, "op": g["op"], "threshold": g["value"], "value": None,
               "passed": False, "note": ""}
        if nv < g.get("min_n", 1):
            res["note"] = f"insufficient houses with a value ({nv} of {len(pop)} < {g.get('min_n', 1)})"
            res["passed"] = g.get("on_insufficient") == "skip"
        else:
            if g["agg"] not in ("t3_contains", "t3_iqr_ratio", "ratio"):
                v = aggregate([metric(r, g["metric"]) for r in pop], g["agg"], g.get("pred"), g.get("valued_only", False))
            res["value"] = v
            res["passed"] = v is not None and OPS[g["op"]](v, g["value"])
            res["note"] = "" if v is not None else "no value"
        out.append(res)
    return out
