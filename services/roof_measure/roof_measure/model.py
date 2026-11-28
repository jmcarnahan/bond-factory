"""The ``bond.roof_model/0.1`` model: the contract constants, totals, validation and the file writer.

The plane engine's adapter (``engine/adapter.py``) builds the model dict; the rules of the contract (section 2) are
checked here, in one place, so the Dart side sees one shape.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from shapely.geometry import Point, Polygon

SCHEMA = "bond.roof_model/0.1"
CORE_EDGE_TYPES = ("eave", "rake", "ridge", "hip", "valley", "step_flashing", "wall_flashing", "parapet",
                   "transition", "unspecified")  # the closed ten of contract 0.2: always in totals.lengths_ft
NEW_EDGE_TYPES = ("flat_edge", "level_change")  # contract 0.4 (engine): a result without them reads as zero
EDGE_TYPES = CORE_EDGE_TYPES + NEW_EDGE_TYPES  # the twelve keys of totals.lengths_ft
UNPRICED_EDGE_TYPES = ("flat_seam",)  # 0.5.1: drawn between two flat pieces of one deck, never priced, in no total
VALID_EDGE_TYPES = EDGE_TYPES + UNPRICED_EDGE_TYPES  # what an edge may be typed
# closed contract vocabulary (FORMS, METHODS); entries the library no longer emits stay until the 0.6.0 contract
FORMS = ("flat", "hip", "gable", "shed")
METHODS = ("lidar_skeleton", "lidar_agent", "solar_agent", "manual", "fixture")


def origin_of(blockset: Any) -> dict[str, Any]:
    """``model.origin``: the frame origin as lat/lng, plus ``epsg`` (the projected CRS of the local frame, contract 0.4)
    when the frame is known, so a point can be moved between WGS84 and the model's feet."""
    out = dict(blockset.origin)
    epsg = (getattr(blockset, "frame", None) or {}).get("epsg")
    if epsg:
        out["epsg"] = int(epsg)
    return out


class ModelError(ValueError):
    """The model breaks a rule of the contract."""


# ----------------------------------------------------------------------------- totals
def pitch_bucket(kind: str, pitch_rise: float) -> float:
    """Contract bucket: 0 for flat or <= 0.5/12, else the pitch rounded to the nearest half."""
    if kind == "flat" or pitch_rise <= 0.5:
        return 0.0
    return round(pitch_rise * 2) / 2


def predominant_pitch(facets: list[dict[str, Any]]) -> tuple[float, float]:
    """(bucket, summed area_sqft) of the bucket with the most area; ties go to the lower pitch."""
    by: dict[float, float] = {}
    for f in facets:
        k = pitch_bucket(f["kind"], f["pitch_rise"])
        by[k] = by.get(k, 0.0) + f["area_sqft"]
    best = (0.0, 0.0)
    for k in sorted(by):
        if by[k] > best[1]:
            best = (k, by[k])
    return best


def _totals(facets: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Model totals. ``lengths_ft`` has all twelve edge-type keys (the ten of 0.2 and ``flat_edge``, ``level_change``)."""
    total = sum(f["area_sqft"] for f in facets)
    pitched = sum(f["area_sqft"] for f in facets if f["kind"] == "sloped")
    flat = sum(f["area_sqft"] for f in facets if f["kind"] == "flat")
    pred = predominant_pitch(facets)
    lengths = {k: 0.0 for k in EDGE_TYPES}
    for e in edges:
        if e["type"] not in UNPRICED_EDGE_TYPES:
            lengths[e["type"]] += e["length_ft"]
    return {"total_area_sqft": total, "pitched_area_sqft": pitched, "flat_area_sqft": flat,
            "predominant_pitch_rise": pred[0], "predominant_pitch_area_sqft": pred[1],
            "squares": total / 100.0, "lengths_ft": lengths}


# ----------------------------------------------------------------------------- validate / io
def validate(model: dict[str, Any]) -> None:
    """Check every rule of contract section 2; raise :class:`ModelError` on the first breach."""

    def need(cond: bool, msg: str) -> None:
        if not cond:
            raise ModelError(msg)

    for k in ("schema", "generated_at", "address", "origin", "north_deg", "units", "source", "blocks", "facets",
              "edges", "holes", "totals", "confidence", "warnings"):
        need(k in model, f"missing top-level key {k!r}")
    need(model["schema"] == SCHEMA, f"schema must be {SCHEMA}")
    need(model["units"] == "ft", "units must be 'ft'")
    need(model["north_deg"] == 0, "north_deg must be 0")
    need(model["source"].get("method") in METHODS, f"source.method must be one of {METHODS}")
    blocks = {b["id"]: b for b in model["blocks"]}
    need(len(blocks) == len(model["blocks"]), "duplicate block ids")
    for b in model["blocks"]:
        need(b["form"] in FORMS, f"block {b['id']}: bad form {b['form']!r}")
        n = len(b["polygon"])
        need(n >= 3, f"block {b['id']}: polygon needs 3 points")
        need(all(0 <= g < n for g in b["gable_edges"]), f"block {b['id']}: gable edge index out of range")
        for key in ("pitch_rise", "plan_area_sqft", "ridge_azimuth_deg", "eave_height_ft"):
            need(key in b, f"block {b['id']}: missing {key}")
    facets = {f["id"]: f for f in model["facets"]}
    need(len(facets) == len(model["facets"]), "duplicate facet ids")
    plan_by_block: dict[str, float] = {}
    for f in model["facets"]:
        need(f["kind"] in ("flat", "sloped"), f"facet {f['id']}: bad kind")
        need(f["block"] in blocks, f"facet {f['id']}: unknown block {f['block']}")
        need(abs(f["area_sqft"] - f["plan_area_sqft"] * math.sqrt(1 + (f["pitch_rise"] / 12) ** 2)) < 0.05
             + 1e-4 * f["area_sqft"], f"facet {f['id']}: area_sqft is not plan area times slope factor")
        need((f["aspect_deg"] is None) == (f["kind"] == "flat"), f"facet {f['id']}: aspect_deg null iff flat")
        plan_by_block[f["block"]] = plan_by_block.get(f["block"], 0.0) + f["plan_area_sqft"]
    for bid, b in blocks.items():
        need(bid in plan_by_block, f"block {bid} has no facet")
        need(abs(plan_by_block[bid] - b["plan_area_sqft"]) <= max(0.5, 0.005 * b["plan_area_sqft"]),
             f"block {bid}: facets do not tile the block polygon")
    lengths: dict[str, float] = {k: 0.0 for k in EDGE_TYPES}
    ids = set()
    for e in model["edges"]:
        need(e["id"] not in ids, f"duplicate edge id {e['id']}")
        ids.add(e["id"])
        need(e["type"] in VALID_EDGE_TYPES, f"edge {e['id']}: bad type {e['type']!r}")
        need(len(e["points"]) == 2, f"edge {e['id']}: must be a two point segment")
        need(1 <= len(e["facets"]) <= 2 and all(i in facets for i in e["facets"]), f"edge {e['id']}: bad facets")
        need(e["length_ft"] + 1e-6 >= math.dist(*e["points"]) - 0.05 - 0.01 * e["length_ft"],
             f"edge {e['id']}: length_ft shorter than its plan length")
        if e["type"] not in UNPRICED_EDGE_TYPES:
            lengths[e["type"]] += e["length_ft"]
    for e in model["edges"]:  # every edge lies on the boundary of one of its facets (hole outlines excepted)
        if e["type"] == "wall_flashing" and model["holes"]:
            continue
        near = min(Polygon(facets[i]["polygon"]).exterior.distance(Point(pt)) for i in e["facets"]
                   for pt in e["points"])
        need(near <= 1.0, f"edge {e['id']} is not on the boundary of its facets (stray spur)")
    for f in model["facets"]:  # no spikes
        pts = f["polygon"]
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
            l1, l2 = math.hypot(*v1), math.hypot(*v2)
            if l1 < 1e-9 or l2 < 1e-9:
                continue
            ang = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))))
            need(ang >= 10.0, f"facet {f['id']} has a spike ({ang:.1f} deg) at vertex {i}")
    t = model["totals"]
    have = set(t["lengths_ft"])
    need(set(CORE_EDGE_TYPES) <= have <= set(EDGE_TYPES),
         "totals.lengths_ft must have the ten keys of contract 0.2 (and may add flat_edge and level_change)")
    for k in EDGE_TYPES:  # a missing 0.4 key counts as zero (results stored before the engine)
        need(abs(t["lengths_ft"].get(k, 0.0) - lengths[k]) <= 0.05, f"totals.lengths_ft.{k} does not match the edges")
    total = sum(f["area_sqft"] for f in model["facets"])
    need(abs(t["total_area_sqft"] - total) <= 0.5, "total_area_sqft does not match the facets")
    need(abs(t["squares"] - t["total_area_sqft"] / 100.0) <= 1e-4, "squares must be total_area_sqft / 100")
    need(abs(t["pitched_area_sqft"] + t["flat_area_sqft"] - t["total_area_sqft"]) <= 0.5,
         "pitched + flat must equal total")
    if model["facets"]:
        bucket, area = predominant_pitch(model["facets"])
        need(t["predominant_pitch_rise"] == bucket and abs(t["predominant_pitch_area_sqft"] - area) <= 0.5,
             "predominant pitch must be the half-step bucket with the largest summed area (ties: lower pitch)")
    need(model["confidence"].get("overall") in ("high", "medium", "low"), "confidence.overall must be high|medium|low")


def _round(o: Any) -> Any:
    if isinstance(o, float):
        return round(o, 5)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_round(v) for v in o]
    return o


def write_model(model: dict[str, Any], path: str | Path) -> None:
    """Validate and write ``model`` with ``indent=1`` (floats rounded to 5 decimals = 0.00003 mm)."""
    validate(model)
    Path(path).write_text(json.dumps(_round(model), indent=1) + "\n")
