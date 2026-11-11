"""Tool schemas and the Workspace for the verifier loop (the agent.py pattern: every number comes from a tool).

Tool results are rounded to 3 dp and every number in them joins ``allowed``; ``finalize`` rejects notes or
adjustments quoting a number that is not known. The verdict is never taken from the model: it is computed from
the totals delta (:func:`verdict_from_delta`) and a different proposal is overridden and noted.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .envelope import totals_from_model
from .model import ModelError, validate
from .verify_merge import merge_collinear, turning_deg, vertex_key

NUMBER_TOL = 0.006
MAX_LLM_MERGES = 3
VERDICTS = ("pass", "adjusted", "fail")
LENGTH_KEYS = ("eave_ft", "rake_ft", "ridge_ft", "hip_ft", "valley_ft", "step_flashing_ft")
VARIANT_KEYS = ("drip_edge_eave_ft", "drip_edge_eave_rake_ft", "ridge_cap_ridge_ft", "ridge_cap_ridge_hip_ft")
MAX_NOTES = 10
MAX_NOTE_CHARS = 300
_ID = re.compile(r"(?<![A-Za-z0-9_])[efbh]\d+(?![\w])")  # edge/facet/block/hole ids only
_NUM = re.compile(r"(?<![\d.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_UNIT = re.compile(r"\s*(?:%|percent|squares?\b|sq\b|sqft|ft\b|feet|foot|in\b|inch|inches|deg|degrees?|\u00b0)", re.IGNORECASE)

TOOLS: list[dict[str, Any]] = [
    {"name": "measure_edges",
     "description": "Per-edge rows {id, type, length_ft, n_points, turning_deg_to_next} and per-type length sums.",
     "input_schema": {"type": "object", "properties": {"edge_ids": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "merge_collinear",
     "description": "Merge runs of tiny nearly collinear same-type edges into one. Bounded: angle_tol_deg <= 5, "
                    "min_len_ft <= 3, at most 3 calls. Returns the adjustments and the new totals.",
     "input_schema": {"type": "object", "required": ["angle_tol_deg", "min_len_ft"],
                      "properties": {"angle_tol_deg": {"type": "number", "maximum": 5},
                                     "min_len_ft": {"type": "number", "maximum": 3}}}},
    {"name": "recompute_totals",
     "description": "Current totals of the working model and the percent change per key against the original.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "finalize_verdict",
     "description": "Finish. Every number in notes and adjustments must come from a tool result.",
     "input_schema": {"type": "object", "required": ["verdict", "notes", "adjustments"],
                      "properties": {"verdict": {"type": "string", "enum": list(VERDICTS)},
                                     "notes": {"type": "array", "items": {"type": "string"}},
                                     "adjustments": {"type": "array", "items": {"type": "object"}}}}},
]


def _r(o: Any, nd: int = 3) -> Any:
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {k: _r(v, nd) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_r(v, nd) for v in o]
    return o


def _numbers(o: Any) -> list[float]:
    if isinstance(o, bool):
        return []
    if isinstance(o, (int, float)):
        return [float(o)]
    if isinstance(o, dict):
        return [n for v in o.values() for n in _numbers(v)]
    if isinstance(o, (list, tuple)):
        return [n for v in o for n in _numbers(v)]
    return []


def delta_pct(original: dict[str, Any], current: dict[str, Any]) -> dict[str, float]:
    out = {}
    for k, o in original.items():
        c = current[k]
        out[k] = round(0.0 if c == o else (100.0 if not o else (c - o) / abs(o) * 100.0), 3)
    return out


def verdict_from_delta(original: dict[str, Any], current: dict[str, Any], orig_lengths: dict[str, float] | None = None,
                       cur_lengths: dict[str, float] | None = None) -> str:
    """fail: area moved > 5% or any edge-type total over 10 ft moved > 10%; adjusted: any total moved; else pass.

    The edge-type check covers all ten types when the model's ``lengths_ft`` dicts are given.
    """
    oa = original["area_sqft"]
    if oa and abs(current["area_sqft"] - oa) / oa > 0.05:
        return "fail"
    pairs = [(original[k], current[k]) for k in LENGTH_KEYS]
    if orig_lengths is not None and cur_lengths is not None:
        pairs += [(orig_lengths[k], cur_lengths.get(k, 0.0)) for k in orig_lengths]
    for o, c in pairs:
        if o > 10.0 and abs(c - o) / o > 0.10:
            return "fail"
    if abs(current["area_sqft"] - oa) > 0.5 or any(abs(current[k] - original[k]) > 0.05
                                                   for k in LENGTH_KEYS + VARIANT_KEYS):
        return "adjusted"
    if current["predominant_pitch"] != original["predominant_pitch"] or current["facets"] != original["facets"]:
        return "adjusted"
    return "pass"


def checker_for(model: dict[str, Any]):
    """``validate`` when the model validates now (so a later failure is ours), else None."""
    try:
        validate(model)
    except Exception:  # noqa: BLE001
        return None
    return validate


class Workspace:
    """The working model, the adjustments so far, and the numbers the model may quote."""

    def __init__(self, model: dict[str, Any], adjustments: list[dict[str, Any]], original_totals: dict[str, Any],
                 angle_tol_deg: float = 3.0, min_len_ft: float = 2.0, original_lengths: dict[str, float] | None = None):
        self.model = model
        self.adjustments = list(adjustments)
        self.original = original_totals
        self.angle_tol_deg = angle_tol_deg
        self.min_len_ft = min_len_ft
        self.original_lengths = dict(original_lengths if original_lengths is not None
                                     else model["totals"]["lengths_ft"])
        self.check = checker_for(model)
        self.allowed: list[float] = [float(angle_tol_deg), float(min_len_ft)]
        self.merges = 0
        self.final: dict[str, Any] | None = None

    def current_totals(self) -> dict[str, Any]:
        return totals_from_model(self.model)

    def verdict(self) -> str:
        return verdict_from_delta(self.original, self.current_totals(), self.original_lengths,
                                  self.model["totals"]["lengths_ft"])

    def is_known(self, v: float) -> bool:
        v = abs(float(v))
        return any(abs(v - abs(a)) <= NUMBER_TOL for a in self.allowed) or self._small_int(v)

    @staticmethod
    def _small_int(v: float) -> bool:
        return float(v).is_integer() and 0 <= v <= 10

    def unknown_in_text(self, text: str) -> list[float]:
        """Numbers in a note that no tool returned. Bare small integers pass; with a unit or % they must be known."""
        text = re.sub(r"(?<=\d)/12\b", "", _ID.sub("", text))  # drop ids and the 12 of a pitch such as 4/12
        bad = []
        for m in _NUM.finditer(text):
            v = abs(float(m.group().replace(",", "")))
            with_unit = _UNIT.match(text, m.end()) is not None
            known = any(abs(v - abs(a)) <= NUMBER_TOL for a in self.allowed)
            if not known and (with_unit or not self._small_int(v)):
                bad.append(v)
        return bad

    # --- tools
    def measure_edges(self, edge_ids: list[str] | None = None) -> dict[str, Any]:
        edges = self.model["edges"]
        deg = Counter(vertex_key(p) for e in edges for p in e["points"])
        at: dict[Any, list[dict[str, Any]]] = {}
        for e in edges:
            for p in e["points"]:
                at.setdefault(vertex_key(p), []).append(e)
        rows = []
        for e in sorted(edges, key=lambda x: x["id"]):
            if edge_ids and e["id"] not in edge_ids:
                continue
            a, b = e["points"]
            turn = None
            for end, other in ((b, a), (a, b)):
                k = vertex_key(end)
                mates = [x for x in at[k] if x is not e and x["type"] == e["type"]]
                if deg[k] == 2 and len(mates) == 1:
                    q = mates[0]["points"]
                    far = q[1] if vertex_key(q[0]) == k else q[0]
                    turn = turning_deg((end[0] - other[0], end[1] - other[1]), (far[0] - end[0], far[1] - end[1]))
                    break
            rows.append({"id": e["id"], "type": e["type"], "length_ft": e["length_ft"], "n_points": len(e["points"]),
                         "turning_deg_to_next": turn})
        sums: dict[str, float] = {}
        for e in edges:
            sums[e["type"]] = sums.get(e["type"], 0.0) + e["length_ft"]
        return {"n_edges": len(edges), "edges": rows, "sum_ft_by_type": sums}

    def recompute_totals(self) -> dict[str, Any]:
        cur = self.current_totals()
        return {"totals": cur, "delta_pct": delta_pct(self.original, cur), "computed_verdict": self.verdict()}

    def merge_collinear(self, angle_tol_deg: float, min_len_ft: float) -> dict[str, Any]:
        if not (0 < float(angle_tol_deg) <= 5 and 0 < float(min_len_ft) <= 3):
            raise ValueError("angle_tol_deg must be in (0, 5] and min_len_ft in (0, 3]")
        if self.merges >= MAX_LLM_MERGES:
            raise ValueError(f"at most {MAX_LLM_MERGES} merge_collinear calls")
        self.merges += 1
        merged, adj = merge_collinear(self.model, float(angle_tol_deg), float(min_len_ft), self.check)
        if self.check is not None:
            try:
                self.check(merged)
            except ModelError as exc:
                return {"error": f"merge rejected, model unchanged: {str(exc)[:160]}",
                        "hint": "try a smaller angle_tol_deg or min_len_ft, or finalize"}
        self.model = merged
        self.adjustments.extend(adj)
        return {"chains_merged": len(adj), "adjustments": adj, **self.recompute_totals()}

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in ("measure_edges", "merge_collinear", "recompute_totals"):
            raise KeyError(f"unknown tool {name!r}")
        res = _r(getattr(self, name)(**args))
        self.allowed.extend(_numbers(res))
        return res

    def finalize(self, args: dict[str, Any]) -> dict[str, Any]:
        """Accept or return ``{"error", "hint"}``. The verdict is recomputed from the delta, never trusted."""
        verdict, notes, adj = args.get("verdict"), args.get("notes"), args.get("adjustments", [])
        if verdict not in VERDICTS or not isinstance(notes, list) or not isinstance(adj, list):
            return {"error": "verdict must be pass|adjusted|fail; notes a list of strings; adjustments a list",
                    "hint": "call finalize_verdict again with those shapes"}
        bad = [n for s in notes for n in self.unknown_in_text(str(s))] + [n for n in _numbers(adj)
                                                                           if not self.is_known(n)]
        if bad:
            return {"error": f"numbers not returned by any tool: {sorted(set(bad))}",
                    "hint": "quote only numbers from tool results (call recompute_totals or measure_edges)"}
        computed = self.verdict()
        out_notes = [str(s)[:MAX_NOTE_CHARS] for s in notes]
        if len(out_notes) > MAX_NOTES or any(len(str(s)) > MAX_NOTE_CHARS for s in notes):
            out_notes = out_notes[:MAX_NOTES - 1] + [f"notes truncated to {MAX_NOTES} of {MAX_NOTE_CHARS} characters"]
        if computed != verdict:
            out_notes.append(f"verdict overridden from {verdict} to {computed} by the totals delta")
        self.final = {"verdict": computed, "proposed": verdict, "notes": out_notes}
        return {"status": "accepted", "verdict": computed}

