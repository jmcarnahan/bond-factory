"""Deterministic step of the verifier: merge runs of tiny, nearly collinear same-type edges.

A chain is a walk over edges of one ``type`` and one ``facets`` set that meet end to end at vertices no other
edge touches. Every interior segment of the chain is at most ``min_len_ft`` long (the two end segments may be
longer) and each turn, and each segment against the chain's overall direction, is at most ``angle_tol_deg``.
The chain becomes one edge, the vertices it swallowed leave the facet polygons, and those facets' areas are
recomputed with the slope factor they already had. Input is never mutated; output is deterministic.
"""

from __future__ import annotations

import copy
import math
from collections import Counter
from collections.abc import Callable
from typing import Any

from .model import _round, _totals

Pt = tuple[float, float]
MAX_CHORD_DEVIATION_FT = 0.25  # a swallowed vertex may sit at most this far off the merged line
EPS = 1e-9


def vertex_key(p: list[float] | tuple[float, float]) -> Pt:
    """A hashable vertex id: coordinates rounded to 4 dp (the 1e-6 ft tolerance of the contract)."""
    return (round(p[0], 4) + 0.0, round(p[1], 4) + 0.0)


def turning_deg(d1: Pt, d2: Pt) -> float:
    """Angle in degrees between two direction vectors (0 = straight on); 0 when either is degenerate."""
    n1, n2 = math.hypot(*d1), math.hypot(*d2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    c = (d1[0] * d2[0] + d1[1] * d2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _dir(a: list[float], b: list[float]) -> Pt:
    return (b[0] - a[0], b[1] - a[1])


def shoelace(poly: list[list[float]]) -> float:
    s = 0.0
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        s += p[0] * q[1] - q[0] * p[1]
    return abs(s) / 2.0


def _oriented(e: dict[str, Any], start: Pt) -> tuple[dict[str, Any], list[float], list[float]]:
    a, b = e["points"]
    return (e, a, b) if vertex_key(a) == start else (e, b, a)


def _walk_paths(group: list[dict[str, Any]], deg: Counter) -> list[list[tuple[dict[str, Any], list[float], list[float]]]]:
    """Maximal end-to-end paths of ``group`` through vertices that exactly two of its edges (and no other) touch."""
    at: dict[Pt, list[dict[str, Any]]] = {}
    for e in group:
        for p in e["points"]:
            at.setdefault(vertex_key(p), []).append(e)

    def linkable(v: Pt) -> bool:
        return deg[v] == 2 and len(at[v]) == 2 and at[v][0] is not at[v][1]

    seen: set[str] = set()
    paths = []
    for e in group:
        if e["id"] in seen:
            continue
        ka, kb = (vertex_key(p) for p in e["points"])
        if linkable(ka) and linkable(kb):
            continue  # interior of a path (or a closed loop, which is left alone)
        start = ka if not linkable(ka) else kb
        path = [_oriented(e, start)]
        seen.add(e["id"])
        v = vertex_key(path[-1][2])
        while linkable(v):
            nxt = next(x for x in at[v] if x is not path[-1][0])
            if nxt["id"] in seen:
                break
            path.append(_oriented(nxt, v))
            seen.add(nxt["id"])
            v = vertex_key(path[-1][2])
        paths.append(path)
    return paths


def _chord_dev(pts: list[list[float]], a: list[float], b: list[float]) -> float:
    """Largest perpendicular distance of ``pts`` from the line a-b (inf when a and b coincide)."""
    n = math.dist(a, b)
    if n < 1e-9:
        return math.inf
    return max(abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / n for p in pts)


def _chains(path: list[tuple[dict[str, Any], list[float], list[float]]], angle_tol: float, min_len: float
            ) -> list[list[tuple[dict[str, Any], list[float], list[float]]]]:
    """Split a path greedily into chains that satisfy the interior-length, angle and chord-deviation rules."""
    out = []
    i = 0
    while i < len(path):
        j = i
        while j + 1 < len(path):
            if j > i and path[j][0]["length_ft"] > min_len + EPS:
                break  # path[j] would become an interior segment but is too long
            cand = path[j + 1]
            if turning_deg(_dir(*path[j][1:]), _dir(*cand[1:])) > angle_tol + EPS:
                break
            overall = _dir(path[i][1], cand[2])
            if any(turning_deg(_dir(*s[1:]), overall) > angle_tol + EPS for s in path[i:j + 2]):
                break
            if _chord_dev([s[1] for s in path[i + 1:j + 2]], path[i][1], cand[2]) > MAX_CHORD_DEVIATION_FT + EPS:
                break
            j += 1
        out.append(path[i:j + 1])
        i = j + 1
    return out


def _find(model: dict[str, Any], angle_tol: float, min_len: float) -> list[dict[str, Any]]:
    edges = model["edges"]
    deg: Counter = Counter(vertex_key(p) for e in edges for p in e["points"])
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = {}
    for e in sorted(edges, key=lambda x: x["id"]):
        groups.setdefault((e["type"], tuple(sorted(e["facets"]))), []).append(e)
    found = []
    for key in sorted(groups):
        for path in _walk_paths(groups[key], deg):
            for chain in _chains(path, angle_tol, min_len):
                if len(chain) < 2:
                    continue
                ids = sorted(s[0]["id"] for s in chain)
                start, end = chain[0][1], chain[-1][2]
                plan = sum(math.dist(s[1], s[2]) for s in chain)
                before = sum(s[0]["length_ft"] for s in chain)
                ratio = max(1.0, before / plan) if plan > 1e-9 else 1.0
                keep = next(s[0] for s in chain if s[0]["id"] == ids[0])
                found.append({"ids": ids, "type": key[0], "facets": list(keep["facets"]), "start": list(start),
                              "end": list(end), "before": before, "after": math.dist(start, end) * ratio,
                              "dead": [vertex_key(s[2]) for s in chain[:-1]]})
    found.sort(key=lambda c: c["ids"])
    return found


def _apply(out: dict[str, Any], ch: dict[str, Any]) -> None:
    """Apply one chain to ``out`` in place (a private copy): edges, facet polygons and areas, totals."""
    gone = set(ch["ids"][1:])
    new = {"id": ch["ids"][0], "type": ch["type"], "points": [ch["start"], ch["end"]], "length_ft": ch["after"],
           "facets": ch["facets"]}
    out["edges"] = [new if e["id"] == new["id"] else e for e in out["edges"] if e["id"] not in gone]
    for f in out["facets"]:
        keep_pts = [p for p in f["polygon"] if not any(math.dist(p, d) <= 1e-3 for d in ch["dead"])]
        if len(keep_pts) == len(f["polygon"]) or len(keep_pts) < 3:
            continue
        old_plan = f["plan_area_sqft"]
        factor = f["area_sqft"] / old_plan if old_plan > 1e-9 else 1.0
        f["polygon"] = keep_pts
        f["plan_area_sqft"] = shoelace(keep_pts)
        f["area_sqft"] = f["plan_area_sqft"] * factor
    out["totals"] = _round(_totals(out["facets"], out["edges"]))
    out["facets"] = _round(out["facets"])
    out["edges"] = _round(out["edges"])


def _passes(check: Callable[[dict[str, Any]], None], model: dict[str, Any]) -> bool:
    try:
        check(model)
    except Exception:  # noqa: BLE001 - any failure means the candidate is not safe to use
        return False
    return True


def merge_collinear(model: dict[str, Any], angle_tol_deg: float, min_len_ft: float,
                    check: Callable[[dict[str, Any]], None] | None = None
                    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return ``(merged deep copy, adjustments)``; the input is untouched.

    With ``check`` (e.g. ``model.validate``) every chain is applied on its own: if ``check`` raises for the
    result the chain is skipped and the others still merge.
    """
    out = copy.deepcopy(model)
    adjustments: list[dict[str, Any]] = []
    for ch in _find(model, angle_tol_deg, min_len_ft):
        trial = copy.deepcopy(out)
        _apply(trial, ch)
        if check is not None and not _passes(check, trial):
            continue  # this chain breaks the model: skip it, keep the others
        out = trial
        adjustments.append({"op": "merge_collinear", "edge_ids": ch["ids"], "edge_type": ch["type"],
                            "length_before_ft": round(ch["before"], 3), "length_after_ft": round(ch["after"], 3),
                            "angle_tol_deg": angle_tol_deg, "min_len_ft": min_len_ft})
    return out, adjustments
