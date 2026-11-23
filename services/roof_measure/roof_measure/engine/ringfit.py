"""Orthogonalise a polygon ring to the wall axes: snap edges to horizontal / vertical, merge runs, drop short edges."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon

_Edge = dict[str, Any]


def _edges_from(ring: np.ndarray, snap_deg: float) -> list[_Edge]:
    """One dict per ring edge: kind H (near-horizontal), V (near-vertical) or O (other), endpoints a, b, length L."""
    es = []
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        d = b - a
        length = float(np.hypot(*d))
        ang = math.degrees(math.atan2(d[1], d[0])) % 180.0
        if min(ang, 180 - ang) <= snap_deg:
            kind = "H"
        elif abs(ang - 90) <= snap_deg:
            kind = "V"
        else:
            kind = "O"
        es.append({"kind": kind, "a": a, "b": b, "L": length})
    return es


def _weight(e: _Edge) -> tuple[float, float]:
    """(length, offset of the edge from its axis) for the length-weighted line fit."""
    return e["L"], (e["a"][1] + e["b"][1]) / 2 if e["kind"] == "H" else (e["a"][0] + e["b"][0]) / 2


def _merge_runs(es: list[_Edge]) -> list[_Edge]:
    """Merge consecutive same-kind H / V edges (also across the ring seam) and fit their common offset."""
    merged: list[_Edge] = []
    for e in es:
        if merged and e["kind"] in "HV" and merged[-1]["kind"] == e["kind"]:
            m = merged[-1]
            m["W"].append(_weight(e))
            m["L"] += e["L"]
            m["b"] = e["b"]
        else:
            e = dict(e)
            if e["kind"] in "HV":
                e["W"] = [_weight(e)]
            merged.append(e)
    if len(merged) > 1 and merged[0]["kind"] in "HV" and merged[0]["kind"] == merged[-1]["kind"]:
        last = merged.pop()
        merged[0]["W"] = last["W"] + merged[0]["W"]
        merged[0]["L"] += last["L"]
        merged[0]["a"] = last["a"]
    for e in merged:
        if e["kind"] in "HV":
            w = np.array(e["W"])
            e["off"] = float((w[:, 0] * w[:, 1]).sum() / w[:, 0].sum())
    return merged


def _line_of(e: _Edge) -> tuple:
    if e["kind"] in "HV":
        return (e["kind"], e["off"])
    return ("O", e["a"], e["b"])


def _as_line(line: tuple) -> tuple[np.ndarray, np.ndarray]:
    if line[0] == "H":
        return np.array([0.0, line[1]]), np.array([1.0, 0.0])
    if line[0] == "V":
        return np.array([line[1], 0.0]), np.array([0.0, 1.0])
    d = line[2] - line[1]
    return line[1], d / (np.hypot(*d) + 1e-12)


def _intersect(l1: tuple, l2: tuple) -> np.ndarray | None:
    p1, d1 = _as_line(l1)
    p2, d2 = _as_line(l2)
    a = np.array([d1, -d2]).T
    if abs(np.linalg.det(a)) < 1e-6:
        return None
    t = np.linalg.solve(a, p2 - p1)
    return p1 + t[0] * d1


def regularise_ring(poly: Polygon, theta: float, snap_deg: float = 15.0, min_edge: float = 0.6,
                    tol: float = 0.22) -> Polygon | None:
    """Orthogonalise ``poly`` to the axes ``theta`` (degrees from +x). Returns a Polygon, or None when degenerate."""
    rot = affinity.rotate(poly, -theta, origin=(0, 0))
    rot = rot.simplify(tol, preserve_topology=True)
    if rot.geom_type != "Polygon" or rot.is_empty:
        return None
    ring = np.array(rot.exterior.coords)[:-1]
    if len(ring) < 4:
        return poly
    es = _edges_from(ring, snap_deg)
    for _ in range(30):
        merged = _merge_runs(es)
        short = [(e["L"], i) for i, e in enumerate(merged) if e["L"] < min_edge]
        if not short or len(merged) <= 4:
            es = merged
            break
        _, k = min(short)
        del merged[k]
        es = merged
    lines = [_line_of(e) for e in es]
    verts = []
    for i in range(len(lines)):
        v = _intersect(lines[i], lines[(i + 1) % len(lines)])
        verts.append(es[i]["b"] if v is None else v)  # parallel neighbours (jog removed): keep the edge end
    if len(verts) < 3:
        return poly
    out = Polygon(verts)
    if not out.is_valid:
        out = out.buffer(0)
        if out.geom_type == "MultiPolygon":
            out = max(out.geoms, key=lambda g: g.area)
    if out.is_empty or out.geom_type != "Polygon":
        return None
    return affinity.rotate(out, theta, origin=(0, 0))
