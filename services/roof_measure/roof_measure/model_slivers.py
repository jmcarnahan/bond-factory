"""Merge a tiny facet with a spike into the neighbour of its own block it shares the longest border with (that has no spike after the merge).

``model.validate`` rejects a facet vertex sharper than 10 degrees. A triangle (or quad) cannot lose its sharp vertex
without ceasing to exist, so the honest repair is to give the sliver to the neighbouring facet of the same block: the
block still tiles exactly, the block pitch is the same, and nothing changes for a facet that never had a spike.

Measured on three real roofs (0.3.0 failures; areas are of the spike facets): 1.3 to 11 sq ft of blocks of 810 to 9937
sq ft, 0.1% to 0.5% of their block. The bounds therefore are an absolute 25 sq ft and 2% of the block, whichever is
smaller: a thin facet that is a real part of the roof (a long narrow hip end) is larger and stays for validate to judge.
Only a facet that would fail validate is touched, so a model that passed before is never changed. A merge is made
only when it leaves no spike (a sliver whose tip is on the outline keeps its tip in the wrong neighbour).
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

SPIKE_DEG = 10.0
MAX_SLIVER_SQFT = 25.0
MAX_SLIVER_SHARE = 0.02  # of the block's plan area
MIN_SHARED_FT = 0.05  # a neighbour must share at least this much border
TOUCH_FT = 0.02  # border points closer than this count as shared
COLLINEAR_DEG = 0.5
Pt = tuple[float, float]


def _angle(a: Pt, b: Pt, c: Pt) -> float:
    v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    l1, l2 = math.hypot(*v1), math.hypot(*v2)
    if l1 < 1e-9 or l2 < 1e-9:
        return 180.0
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def has_spike(ring: list[Any]) -> bool:
    """True when a vertex of the ring is sharper than the bound ``validate`` enforces."""
    n = len(ring)
    return any(_angle(ring[i - 1], ring[i], ring[(i + 1) % n]) < SPIKE_DEG for i in range(n))


def _straighten(coords: list[Pt]) -> list[Pt]:
    """Drop the vertices of a closed ring (no repeated last point) that lie on a straight line."""
    ring = list(coords)
    changed = True
    while changed and len(ring) > 3:
        changed = False
        for i in range(len(ring)):
            if 180.0 - _angle(ring[i - 1], ring[i], ring[(i + 1) % len(ring)]) < COLLINEAR_DEG:
                del ring[i]
                changed = True
                break
    return ring


def _merge_pair(sliver: dict[str, Any], keep: dict[str, Any]) -> list[Pt] | None:
    """The ring of the union of two facets when it is one simple polygon without holes, else None."""
    union = unary_union([Polygon(sliver["polygon"]), Polygon(keep["polygon"])])
    if isinstance(union, MultiPolygon) or union.geom_type != "Polygon" or union.interiors or not union.is_valid:
        return None
    ring = _straighten([(float(x), float(y)) for x, y in orient(union).exterior.coords][:-1])
    return ring if len(ring) >= 3 else None


def _merge_target(sliver: dict[str, Any], others: list[dict[str, Any]]) -> tuple[dict[str, Any], list[Pt]] | None:
    """The neighbour sharing the longest border whose union with the sliver has no spike left, with that union.

    A sliver whose sharp tip lies on the outline keeps its tip when merged into the wrong neighbour, so the
    neighbours are tried longest border first and only a merge that removes the spike counts.
    """
    border = Polygon(sliver["polygon"]).exterior
    shared = [(border.intersection(Polygon(o["polygon"]).exterior.buffer(TOUCH_FT)).length, i)
              for i, o in enumerate(others)]
    for length, i in sorted(shared, reverse=True):
        if length < MIN_SHARED_FT:
            break
        union = _merge_pair(sliver, others[i])
        if union is not None and not has_spike(union):
            return others[i], union
    return None


def _reassign_edges(edges: list[dict[str, Any]], sliver_id: str, keep_id: str) -> None:
    """Edges of the sliver now belong to the kept facet; an edge between the two vanishes with the border."""
    out: list[dict[str, Any]] = []
    for e in edges:
        if sliver_id in e["facets"]:
            facets = list(dict.fromkeys(keep_id if f == sliver_id else f for f in e["facets"]))
            if len(e["facets"]) == 2 and len(facets) == 1:
                continue  # the border between the two merged facets is no longer an edge
            e["facets"] = facets
        out.append(e)
    edges[:] = out


def merge_slivers(facets: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    """Merge every spike facet under the bounds into a same-block neighbour; one note per merge. Mutates in place."""
    notes: list[str] = []
    block_area: dict[Any, float] = {}
    for f in facets:
        block_area[f.get("block")] = block_area.get(f.get("block"), 0.0) + Polygon(f["polygon"]).area
    for _ in range(len(facets)):  # one merge per round; a merge may expose another spike
        merged = False
        for f in sorted(facets, key=lambda g: Polygon(g["polygon"]).area):
            ring = [(float(x), float(y)) for x, y in f["polygon"]]
            area = Polygon(ring).area
            limit = min(MAX_SLIVER_SQFT, MAX_SLIVER_SHARE * block_area.get(f.get("block"), 0.0))
            if not has_spike(ring) or area > limit or len(facets) < 2:
                continue
            others = [o for o in facets if o is not f and o.get("block") == f.get("block")]
            target = _merge_target(f, others)
            if target is None:
                continue
            keep, union = target
            keep["polygon"] = [list(p) for p in union]
            plan = Polygon(union).area
            keep["plan_area_sqft"] = plan
            keep["area_sqft"] = plan * math.sqrt(1 + (keep["pitch_rise"] / 12.0) ** 2)
            _reassign_edges(edges, f["id"], keep["id"])
            facets.remove(f)
            notes.append(f"facet {f['id']}: sliver merged into facet {keep['id']}")
            merged = True
            break
        if not merged:
            break
    return notes
