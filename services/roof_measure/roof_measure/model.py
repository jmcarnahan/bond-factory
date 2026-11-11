"""Roof blocks -> the ``bond.roof_model/0.1`` JSON (docs/contracts/roof_model.md).

WHY one builder for every method: LiDAR rules, the Solar+Claude agent and the hand-made
fixtures all end as a list of ``RoofBlock``. Facets, typed edges, totals and the validation
live here so the three paths cannot drift apart and the Dart side sees one shape.

Edge typing follows contract section 3. Each block contributes its boundary segments; every
segment is cut where a neighbouring block begins or ends and the piece is typed by comparing
the roof levels either side of it:

* flat beside flat, same level -> ``eave`` (emitted once; the reference report draws these as eaves)
* lower block beside a higher block (step > 1 ft) -> ``wall_flashing`` for a flat block,
  ``step_flashing`` for a sloped block; the lower block owns the edge
* sloped beside same level -> the sloped block's own type (eave, rake, shed ridge)
* nothing beside it -> the block's own type; a flat block's outline edge is ``parapet``
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from .classify import WALL_STEP_FT, BlockSet, Classification, RoofBlock, assign_levels
from .model_cleanup import clean_facets
from .skeleton import block_geometry

log = logging.getLogger(__name__)

SCHEMA = "bond.roof_model/0.1"
EDGE_TYPES = ("eave", "rake", "ridge", "hip", "valley", "step_flashing", "wall_flashing", "parapet",
              "transition", "unspecified")
FORMS = ("flat", "hip", "gable", "shed")
METHODS = ("lidar_skeleton", "lidar_agent", "solar_agent", "manual", "fixture")
NEIGHBOUR_TOL_FT = 0.8  # blocks closer than this share a boundary
MIN_PIECE_FT = 1.2  # a neighbour must run this far along an edge to split it
MIN_EDGE_FT = 0.5  # shorter edges are numerical debris and are dropped


class ModelError(ValueError):
    """The model breaks a rule of the contract."""


@dataclass
class _Blk:
    idx: int
    rb: RoofBlock
    poly: Polygon
    geom: dict[str, Any]
    fids: list[str]
    facet_polys: list[Polygon]

    def facet_at(self, pt: Point) -> int:
        return min(range(len(self.facet_polys)), key=lambda i: self.facet_polys[i].distance(pt))

    def level_at(self, x: float, y: float) -> float:
        """Absolute roof height at a plan point (flat: its level; sloped: eave level + plane)."""
        base = self.rb.level_ft or 0.0
        if self.rb.form == "flat":
            return base
        f = self.geom["facets"][self.facet_at(Point(x, y))]
        c = f["plane"]
        return base + c[0] + c[1] * x + c[2] * y


def _ccw(ring: list[tuple[float, float]]) -> list[list[float]]:
    pts = list(ring)
    a = 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                  for i in range(len(pts)))
    if a < 0:
        pts = pts[::-1]
    return [[float(x), float(y)] for x, y in pts]


def _cleanup_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join collinear neighbours of one type and facet pair, then drop debris shorter than 0.5 ft.

    WHY: outlines come in many small segments; one straight run of eave should be one edge so
    the diagram prints one label ("hide no more than 30% of labels").
    """
    edges = list(edges)
    changed = True
    while changed:
        changed = False
        for i in range(len(edges)):
            for j in range(i + 1, len(edges)):
                a, b = edges[i], edges[j]
                if a["type"] != b["type"] or set(a["facets"]) != set(b["facets"]):
                    continue
                joined = _try_join(a, b)
                if joined is not None:
                    edges[i] = joined
                    del edges[j]
                    changed = True
                    break
            if changed:
                break
    kept = [e for e in edges if e["length_ft"] >= MIN_EDGE_FT]
    if len(kept) != len(edges):
        log.info("dropped %d edge(s) shorter than %.1f ft", len(edges) - len(kept), MIN_EDGE_FT)
    return kept


def _try_join(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    for ai in (0, 1):
        for bi in (0, 1):
            shared_a, shared_b = a["points"][ai], b["points"][bi]
            if math.dist(shared_a, shared_b) > 0.1:
                continue
            fa, fb = a["points"][1 - ai], b["points"][1 - bi]
            line = LineString([fa, fb])
            if line.length < 1e-9 or line.distance(Point(shared_a)) > 0.2:
                continue
            if (shared_a[0] - fa[0]) * (fb[0] - shared_a[0]) + (shared_a[1] - fa[1]) * (fb[1] - shared_a[1]) <= 0:
                continue
            return {"type": a["type"], "points": [fa, fb], "length_ft": a["length_ft"] + b["length_ft"],
                    "facets": a["facets"]}
    return None


def border_steps(bs: BlockSet) -> dict[tuple[str, str], float]:
    """Signed level step (b minus a, ft) across each LiDAR border, both directions.

    ``step_ft`` in the file is a magnitude; the signed value comes from ``extra.border_signed_step_ft``
    when present, else from the block means.
    """
    signed = (bs.extra or {}).get("border_signed_step_ft", {})
    z = {b.id: b.mean_z_ft for b in bs.blocks}
    out: dict[tuple[str, str], float] = {}
    for br in bs.borders:
        a, b = br["a"], br["b"]
        if f"{a}|{b}" in signed:
            v = float(signed[f"{a}|{b}"])
        else:
            mag = abs(float(br.get("step_ft", 0.0)))
            v = mag if z.get(b, 0.0) >= z.get(a, 0.0) else -mag
        out[(a, b)] = v
        out[(b, a)] = -v
    return out


def build_model(blockset: BlockSet, roof_blocks: list[RoofBlock], source: dict[str, Any] | None = None,
                diagnostics: Classification | None = None) -> dict[str, Any]:
    """Assemble the contract model for ``roof_blocks`` over ``blockset``.

    ``source`` may carry ``method`` (default ``lidar_skeleton``), ``solar`` and ``agent`` info;
    ``diagnostics`` supplies the notes, warnings and gap-fill share of the classifier.
    """
    source = dict(source or {})
    method = source.get("method", "lidar_skeleton")
    assign_levels(roof_blocks, blockset)

    blks: list[_Blk] = []
    facets_out: list[dict[str, Any]] = []
    for rb in roof_blocks:
        geom = block_geometry(rb.form, rb.polygon, rb.pitch_rise, rb.gable_edges, rb.aspect_deg)
        fids: list[str] = []
        fpolys: list[Polygon] = []
        for f in geom["facets"]:
            fid = f"f{len(facets_out) + 1}"
            fids.append(fid)
            fpolys.append(Polygon(f["polygon_xy"]))
            facets_out.append({
                "id": fid, "block": rb.id, "kind": "flat" if rb.form == "flat" else "sloped",
                "polygon": _ccw(f["polygon_xy"]), "pitch_rise": 0.0 if rb.form == "flat" else rb.pitch_rise,
                "aspect_deg": None if rb.form == "flat" else f["aspect_deg"],
                "plan_area_sqft": f["plan_area"], "area_sqft": f["area"]})
        blks.append(_Blk(len(blks), rb, rb.poly, geom, fids, fpolys))

    edges = _build_edges(blks, border_steps(blockset))
    cleanup_notes = clean_facets(facets_out, edges)  # sliver spikes would fail validate; see model_cleanup.py
    totals = _totals(facets_out, edges)
    notes, warnings = _notes(blockset, blks, edges, diagnostics, method, source)
    warnings = [*warnings, *cleanup_notes]
    confidence = _confidence(blockset, diagnostics, source, blks)

    meta = blockset.footprint_meta
    lidar = blockset.lidar
    model: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "address": dict(blockset.address),
        "origin": dict(blockset.origin),
        "north_deg": 0,
        "units": "ft",
        "source": {
            "method": method,
            "footprint": {"provider": meta.get("provider"), "id": str(meta.get("id")) if meta.get("id") is not None else None,
                          "area_sqft": meta.get("area_sqft", Polygon(blockset.footprint_ft).area)},
            "lidar": ({**{k: lidar.get(k) for k in ("project", "acquired", "points_on_roof", "density_per_m2")},
                       "fitted_area_sqft": (diagnostics.fitted_area_sqft if diagnostics and diagnostics.fitted_area_sqft
                                            else unary_union([b.poly for b in blockset.blocks]).area
                                            if blockset.blocks else 0.0)}
                      if lidar and method != "solar_agent" else None),
            "solar": source.get("solar"),
        },
        "blocks": [b.rb.to_dict() | {"polygon": _ccw(b.rb.polygon)} for b in blks],
        "facets": facets_out,
        "edges": [{"id": f"e{i}", "type": e["type"], "points": [list(e["points"][0]), list(e["points"][1])],
                   "length_ft": e["length_ft"], "facets": e["facets"]} for i, e in enumerate(edges, start=1)],
        "holes": [],
        "totals": totals,
        "confidence": {"overall": confidence, "notes": notes},
        "warnings": warnings,
        "debug": {},
    }
    if source.get("agent"):
        model["debug"]["agent"] = source["agent"]
    validate(model)
    return model


# ----------------------------------------------------------------------------- edges
def _build_edges(blks: list[_Blk], steps: dict[tuple[str, str], float]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for a in blks:
        for e in a.geom["edges"]:
            if len(e["faces"]) == 2:  # interior skeleton edge: ridge / hip / valley
                (x1, y1, _), (x2, y2, _) = e["polyline_xyz"][0], e["polyline_xyz"][1]
                out.append({"type": e["type"], "points": [(x1, y1), (x2, y2)], "length_ft": e["length"],
                            "facets": [a.fids[e["faces"][0]], a.fids[e["faces"][1]]]})
                continue
            out.extend(_boundary_pieces(a, e, blks, steps))
    return _cleanup_edges(out)


def _boundary_pieces(a: _Blk, e: dict[str, Any], blks: list[_Blk],
                     steps: dict[tuple[str, str], float]) -> list[dict[str, Any]]:
    (px, py, pz), (qx, qy, qz) = e["polyline_xyz"][0], e["polyline_xyz"][1]
    seg = LineString([(px, py), (qx, qy)])
    length = seg.length
    if length < 1e-9:
        return []
    cuts: list[tuple[float, float, _Blk]] = []
    for b in blks:
        if b is a:
            continue
        if b.poly.distance(seg) > NEIGHBOUR_TOL_FT:
            continue
        inter = seg.intersection(b.poly.buffer(NEIGHBOUR_TOL_FT))
        for part in ([inter] if inter.geom_type == "LineString" else list(getattr(inter, "geoms", []))):
            if part.geom_type != "LineString" or part.length < MIN_PIECE_FT:
                continue
            t0 = seg.project(Point(part.coords[0])) / length
            t1 = seg.project(Point(part.coords[-1])) / length
            cuts.append((min(t0, t1), max(t0, t1), b))
    cuts.sort(key=lambda c: c[0])
    spans: list[tuple[float, float, _Blk | None]] = []
    cursor = 0.0
    for t0, t1, b in cuts:
        t0 = max(t0, cursor)
        if (t1 - t0) * length < MIN_PIECE_FT:
            continue
        if t0 > cursor and (t0 - cursor) * length >= MIN_EDGE_FT:
            spans.append((cursor, t0, None))
        spans.append((t0, t1, b))
        cursor = t1
    if cursor < 1.0 and (1.0 - cursor) * length >= MIN_EDGE_FT:
        spans.append((cursor, 1.0, None))
    if not spans:
        spans = [(0.0, 1.0, None)]
    pieces: list[dict[str, Any]] = []
    for t0, t1, b in spans:
        p = (px + (qx - px) * t0, py + (qy - py) * t0)
        q = (px + (qx - px) * t1, py + (qy - py) * t1)
        piece = _type_piece(a, e, b, p, q, (pz + (qz - pz) * t0, pz + (qz - pz) * t1), steps)
        if piece:
            pieces.append(piece)
    return pieces


def _type_piece(a: _Blk, e: dict[str, Any], b: _Blk | None, p: tuple[float, float], q: tuple[float, float],
                zrel: tuple[float, float], steps: dict[tuple[str, str], float]) -> dict[str, Any] | None:
    fa = a.fids[e["faces"][0]]
    plan = math.dist(p, q)
    length = math.hypot(plan, zrel[1] - zrel[0]) if a.rb.form != "flat" else plan
    hint = e["type"]
    if b is None:
        typ = "parapet" if hint == "outline" else hint
        return {"type": typ, "points": [p, q], "length_ft": length, "facets": [fa]}
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    diff = b.level_at(mx, my) - a.level_at(mx, my)
    for sa in a.rb.source_blocks:  # the LiDAR border step beats a difference of block means
        for sb in b.rb.source_blocks:
            if (sa, sb) in steps:
                diff = steps[(sa, sb)]
    fb = b.fids[b.facet_at(Point(mx, my))]
    a_flat, b_flat = a.rb.form == "flat", b.rb.form == "flat"
    if a.rb.form == "shed" and b_flat:  # awning against the higher flat: top is flashed, sides stay rakes
        typ = "step_flashing" if hint == "ridge" else hint
    elif a_flat and b_flat:  # the reference report draws every flat-to-flat line as an eave, whatever the level step
        if a.idx > b.idx:
            return None
        typ = "eave"
    elif diff > WALL_STEP_FT:  # neighbour higher: this (lower) block owns the flashing
        typ = "wall_flashing" if a_flat else "step_flashing"
    elif diff < -WALL_STEP_FT:
        return None  # the lower neighbour emits this edge
    elif a_flat:
        return None  # the sloped neighbour emits it with its own type
    elif b_flat or a.idx < b.idx:
        typ = "eave" if hint == "outline" else hint
    else:
        return None
    return {"type": typ, "points": [p, q], "length_ft": length, "facets": [fa, fb]}


# ----------------------------------------------------------------------------- totals / notes
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
    total = sum(f["area_sqft"] for f in facets)
    pitched = sum(f["area_sqft"] for f in facets if f["kind"] == "sloped")
    flat = sum(f["area_sqft"] for f in facets if f["kind"] == "flat")
    pred = predominant_pitch(facets)
    lengths = {k: 0.0 for k in EDGE_TYPES}
    for e in edges:
        lengths[e["type"]] += e["length_ft"]
    return {"total_area_sqft": total, "pitched_area_sqft": pitched, "flat_area_sqft": flat,
            "predominant_pitch_rise": pred[0], "predominant_pitch_area_sqft": pred[1],
            "squares": total / 100.0, "lengths_ft": lengths}


def _notes(blockset: BlockSet, blks: list[_Blk], edges: list[dict[str, Any]], diag: Classification | None,
           method: str, source: dict[str, Any]) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    warnings: list[str] = []
    kinds = {e["type"] for e in edges}
    if "parapet" in kinds:
        notes.append("Parapet assigned by rule: flat roof edge on the outline (height not measured).")
    wall = sum(e["length_ft"] for e in edges if e["type"] == "wall_flashing")
    notes.append(f"Wall flashing is not derivable from this data ({wall:.0f} ft here): LiDAR resolves no wall "
                 "steps and skylight/curb openings are not modelled.")
    notes.append("Total area includes the roof overhang beyond the county wall line (blocks may extend up to "
                 "1 m past the footprint).")
    if any(b.rb.form == "shed" for b in blks):
        notes.append("Awnings are small low slopes next to the outline; verify extent and pitch on site.")
    if diag:
        notes.extend(diag.notes)
        warnings.extend(diag.warnings)
    notes.extend(n for n in source.get("notes", []) if n not in notes)
    warnings.extend(w for w in source.get("warnings", []) if w not in warnings)
    if method == "solar_agent" and not source.get("solar"):
        warnings.append("Solar evidence was not live (fixture or deterministic path).")
    if not blockset.footprint_meta:
        warnings.append("Footprint provenance is unknown.")
    return notes, warnings


def _confidence(blockset: BlockSet, diag: Classification | None, source: dict[str, Any],
                blks: list[_Blk]) -> str:
    score = 2  # 3 high, 2 medium, 1 low
    if diag and diag.gap_filled_pct > 25:
        score -= 1
    if diag and (diag.warnings or diag.uncovered_pct > 1.0):
        score -= 1
    if source.get("confidence") == "low" or any(b.rb.confidence == "low" and b.rb.form != "shed" for b in blks):
        score -= 1
    density = (blockset.lidar or {}).get("density_per_m2") or 0
    if score == 2 and density >= 8 and diag and diag.gap_filled_pct < 5:
        score = 3
    return {3: "high", 2: "medium"}.get(score, "low")


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
        need(e["type"] in EDGE_TYPES, f"edge {e['id']}: bad type {e['type']!r}")
        need(len(e["points"]) == 2, f"edge {e['id']}: must be a two point segment")
        need(1 <= len(e["facets"]) <= 2 and all(i in facets for i in e["facets"]), f"edge {e['id']}: bad facets")
        need(e["length_ft"] + 1e-6 >= math.dist(*e["points"]) - 0.05 - 0.01 * e["length_ft"],
             f"edge {e['id']}: length_ft shorter than its plan length")
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
    need(set(t["lengths_ft"]) == set(EDGE_TYPES), "totals.lengths_ft must have all ten keys")
    for k in EDGE_TYPES:
        need(abs(t["lengths_ft"][k] - lengths[k]) <= 0.05, f"totals.lengths_ft.{k} does not match the edges")
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
