"""Cleanup pass before validation: drop sliver spikes and near-duplicate vertices from facet polygons.

``model.validate`` rejects a facet vertex sharper than 10 degrees. The skeleton can produce such a vertex on a thin
facet; this pass removes it when that is cheap (the polygon stays simple and loses under 0.5% of its area) and fixes
what touches it: edges that ended at a removed spike tip lose this facet, and are dropped when no facet is left.
Near-duplicate vertices (closer than 0.05 ft) are merged and the edges that ended on them are snapped to the kept one.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon

SPIKE_DEG = 10.0  # the bound validate enforces on every facet vertex
DUP_FT = 0.05
MAX_AREA_LOSS = 0.005
Pt = tuple[float, float]


def interior_angle(a: Pt, b: Pt, c: Pt) -> float:
    """Angle at ``b`` in degrees (180 = straight); 180 for a degenerate corner so it is never removed."""
    v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    l1, l2 = math.hypot(*v1), math.hypot(*v2)
    if l1 < 1e-9 or l2 < 1e-9:
        return 180.0
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _near(p: Any, q: Any, tol: float) -> bool:
    return math.dist(p, q) <= tol


def _dedupe(pts: list[Pt]) -> tuple[list[Pt], dict[Pt, Pt]]:
    """Merge consecutive vertices closer than DUP_FT (wrapping); returns the ring and dropped -> kept."""
    out: list[Pt] = []
    moved: dict[Pt, Pt] = {}
    for p in pts:
        if out and _near(out[-1], p, DUP_FT):
            moved[p] = out[-1]
        else:
            out.append(p)
    while len(out) > 1 and _near(out[0], out[-1], DUP_FT):
        moved[out[-1]] = out[0]
        out.pop()
    return out, moved


def _snap_edges(edges: list[dict[str, Any]], moved: dict[Pt, Pt]) -> None:
    for e in edges:
        e["points"] = [list(moved.get(tuple(p), tuple(p))) for p in e["points"]]
    edges[:] = [e for e in edges if math.dist(*e["points"]) > 1e-9]


def _drop_tip(edges: list[dict[str, Any]], facet_id: str, tip: Pt) -> None:
    for e in edges:
        if facet_id in e["facets"] and any(_near(p, tip, 1e-6) for p in e["points"]):
            e["facets"] = [f for f in e["facets"] if f != facet_id]
    edges[:] = [e for e in edges if e["facets"]]


def clean_facets(facets: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    """Mutate ``facets`` and ``edges`` in place; return one note per removed sliver vertex."""
    notes: list[str] = []
    for f in facets:
        ring: list[Pt] = [(float(x), float(y)) for x, y in f["polygon"]]
        ring, moved = _dedupe(ring)
        if moved:
            _snap_edges(edges, moved)
        changed = bool(moved)
        while len(ring) > 3:
            area = Polygon(ring).area
            angles = [(interior_angle(ring[i - 1], ring[i], ring[(i + 1) % len(ring)]), i) for i in range(len(ring))]
            angle, i = min(angles)
            if angle >= SPIKE_DEG:
                break
            trial = ring[:i] + ring[i + 1:]
            poly = Polygon(trial)
            if not poly.is_valid or area <= 0 or (area - poly.area) / area >= MAX_AREA_LOSS:
                break
            _drop_tip(edges, f["id"], ring[i])
            notes.append(f"facet {f['id']}: sliver vertex removed")
            ring, changed = trial, True
        if changed:
            f["polygon"] = [list(p) for p in ring]
            plan = Polygon(ring).area
            f["plan_area_sqft"] = plan
            f["area_sqft"] = plan * math.sqrt(1 + (f["pitch_rise"] / 12.0) ** 2)
    return notes
