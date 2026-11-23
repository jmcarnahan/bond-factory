"""Schema check of an engine's result.json. Anything malformed is ``invalid`` (distinct from a refusal, which is a valid
result with no facets and a verdict) and fails the "invalid or crashed = 0" gate."""

from __future__ import annotations

import math
from typing import Any

MAX_ABS_M = 1e5  # local metres; larger is a corrupt coordinate


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= MAX_ABS_M


def _ring_ok(ring) -> bool:
    return isinstance(ring, list) and len(ring) >= 3 and all(isinstance(p, (list, tuple)) and len(p) >= 2 and all(_finite(c) for c in p[:2])
                                                          for p in ring)


def problems(res: Any) -> list[str]:
    """Every reason a parsed result.json is malformed (empty list = valid)."""
    if not isinstance(res, dict):
        return [f"result is a {type(res).__name__}, not an object"]
    out: list[str] = []
    fs = res.get("facets")
    if not isinstance(fs, list):
        return ["facets missing or not a list"]
    for i, f in enumerate(fs):
        if not isinstance(f, dict):
            out.append(f"facet {i} is not an object")
            continue
        poly = f.get("polygon")
        if not (_ring_ok(poly) or (isinstance(poly, list) and poly and all(_ring_ok(r) for r in poly))):
            out.append(f"facet {i}: bad polygon")
        pl = f.get("plane")
        if not (isinstance(pl, (list, tuple)) and len(pl) == 3 and all(_finite(c) for c in pl)):
            out.append(f"facet {i}: missing or non-finite plane")
    es = res.get("edges", [])
    if not isinstance(es, list):
        out.append("edges not a list")
    else:
        for i, e in enumerate(es):
            if not (isinstance(e, dict) and all(isinstance(e.get(k), (list, tuple)) and len(e[k]) >= 2 and all(_finite(c) for c in e[k])
                                                for k in ("p0", "p1"))):
                out.append(f"edge {i}: bad end points")
    ol = res.get("roof_outline")
    if ol not in (None, []) and not (_ring_ok(ol) or (isinstance(ol, list) and all(_ring_ok(r) for r in ol))):
        out.append("roof_outline malformed")
    diag = res.get("diagnostics")
    if diag is not None and not isinstance(diag, dict):
        out.append("diagnostics is not an object")
    elif isinstance(diag, dict) and isinstance(diag.get("quality"), dict):
        v = diag["quality"].get("verdict")
        if v is not None and not isinstance(v, str):
            out.append("verdict is not a string")
    if not isinstance(res.get("totals", {}), dict):
        out.append("totals is not an object")
    return out[:8]
