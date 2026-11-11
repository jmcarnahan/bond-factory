"""Claude agent that decides the roof form of each part of a building, with tools for every number.

Design (research: solar-agent-track/agent_design.md): the model is a DECISION layer. It reads
evidence (Google Solar segments or the LiDAR block table) placed on the footprint in feet and
decides, per region, flat / hip / gable / shed, which footprint edges are gable ends, and which
segments belong together. It never writes a length, area, angle or polygon: polygons live in a
server-side registry and are referred to by id, and every number it passes back (pitch, aspect)
must equal a number the evidence or a tool returned (the harness rejects anything else).

The loop is a plain Messages API tool-use loop with a hard cap on rounds. The output is a list
of :class:`RoofBlock` that then goes through the same ``complete_tiling`` and ``build_model`` as
the deterministic path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .classify import BlockSet, RoofBlock, complete_tiling, polygons_of, ridge_azimuth, ring_of
from .deadline import Deadline
from .skeleton import block_geometry, hip_roof_edges, measure, rect_fit, signed_area, split_footprint

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
MAX_ROUNDS = 12
MAX_TOKENS = 6000
NUMBER_TOL = 0.006

SYSTEM_PROMPT = """You are a roof-geometry analyst. You receive a building footprint (vertices in feet, x east, \
y north), an EVIDENCE table of roof segments placed on that footprint (Google Solar API segments, or LiDAR \
surface blocks), and tools. Decide, for each part of the roof, its form (flat, hip, gable, shed) and, for \
gables, which polygon edges are the gable ends. Tools produce every number.

HARD RULES
1. Never estimate, convert, round or compute a length, area, angle, pitch or coordinate yourself. Polygons exist \
only in the registry and are referred to by polygon_id ("footprint", "p1", ...). Every pitch_rise and aspect_deg \
you pass to finalize must be copied exactly from the evidence table or a tool result.
2. Form from evidence. Look at sloped segments (form_hint sloped / kind sloped) in each spatial cluster and count \
distinct azimuths: about 4 azimuths 90 deg apart = hip; 2 azimuths 180 deg apart = gable (the gable ends are the \
polygon edges whose outward bearing is perpendicular to the azimuths; use measure to read edge bearings); 1 azimuth \
= shed. Pitch under 2 deg = flat. A sloped segment whose centre is outside the footprint (inside_footprint false) \
or small and low beside the outline is an awning: a separate shed block.
3. Locate a block with region_from_segments (polygon of the segments' extent), then clean it with rect_fit when \
the outline has small jogs, or cut it with propose_split. Verify with the tool's area numbers that the block's \
plan area is within about 5 percent of the segments' ground area; if not, adjust and retry at most twice.
4. Get the pitch with pitch_rise_from_segments over the segments of the block.
5. Check a hip or gable with hip_roof_edges before finalizing.
6. You need not list flat roofs: the harness turns footprint area you do not claim into flat blocks. List one only \
to override.
7. If the evidence is ambiguous (3 or more than 4 azimuths, area mismatch over 8 percent), keep your best guess, \
set confidence low and say exactly what is uncertain in warnings. Do not invent features (dormers, chimneys, \
parapet heights).
8. Be efficient: call independent tools in the same turn. You have at most 12 rounds, finish in about 4. \
End by calling finalize exactly once."""

TOOLS: list[dict[str, Any]] = [
    {"name": "measure", "description": "Area, perimeter, bounds and per-edge index, length and outward compass "
     "bearing of a registered polygon.",
     "input_schema": {"type": "object", "properties": {"polygon_id": {"type": "string"}},
                      "required": ["polygon_id"]}},
    {"name": "propose_split", "description": "Split a registered polygon by the infinite line through two points "
     "(feet). Registers the parts as new polygons (largest first) and returns their ids and areas.",
     "input_schema": {"type": "object", "properties": {
         "polygon_id": {"type": "string"},
         "line_ft": {"type": "array", "items": {"type": "array", "items": {"type": "number"}, "minItems": 2,
                                                  "maxItems": 2}, "minItems": 2, "maxItems": 2}},
         "required": ["polygon_id", "line_ft"]}},
    {"name": "region_from_segments", "description": "Register the polygon covering the given evidence segment "
     "ids (their union, clipped to the footprint unless the segments are awnings outside it). Returns polygon "
     "id(s) with area and the segments' summed ground area for the 5 percent check.",
     "input_schema": {"type": "object", "properties": {"segment_ids": {"type": "array", "items": {"type": "string"}}},
                      "required": ["segment_ids"]}},
    {"name": "rect_fit", "description": "Register the minimum rotated rectangle of a polygon (removes jogs under "
     "2 ft). Returns the new id, its sides and area.",
     "input_schema": {"type": "object", "properties": {"polygon_id": {"type": "string"}},
                      "required": ["polygon_id"]}},
    {"name": "pitch_rise_from_segments", "description": "Area-weighted mean pitch (inches of rise per 12) of the "
     "given evidence segments, with min, max and spread.",
     "input_schema": {"type": "object", "properties": {"segment_ids": {"type": "array", "items": {"type": "string"}}},
                      "required": ["segment_ids"]}},
    {"name": "hip_roof_edges", "description": "Straight-skeleton roof over a registered polygon at uniform pitch. "
     "gable_edges are polygon edge indices that are gable ends. Returns eave, rake, ridge, hip and valley lengths "
     "(feet) and the true roof area.",
     "input_schema": {"type": "object", "properties": {
         "polygon_id": {"type": "string"}, "pitch_rise": {"type": "number"},
         "gable_edges": {"type": "array", "items": {"type": "integer"}}},
         "required": ["polygon_id", "pitch_rise"]}},
    {"name": "finalize", "description": "Submit the decision. One entry per roof block you claim (hip, gable, "
     "shed awnings, optional flat overrides).",
     "input_schema": {"type": "object", "properties": {
         "blocks": {"type": "array", "items": {"type": "object", "properties": {
             "polygon_id": {"type": "string"},
             "form": {"type": "string", "enum": ["flat", "hip", "gable", "shed"]},
             "pitch_rise": {"type": "number"},
             "gable_edges": {"type": "array", "items": {"type": "integer"}},
             "aspect_deg": {"type": "number", "description": "shed only: the segment azimuth, copied from evidence"},
             "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
             "evidence": {"type": "array", "items": {"type": "string"}}},
             "required": ["polygon_id", "form", "confidence", "evidence"]}},
         "warnings": {"type": "array", "items": {"type": "string"}}},
         "required": ["blocks"]}},
]


class AgentError(RuntimeError):
    """The agent did not produce an acceptable answer."""


@dataclass
class AgentResult:
    blocks: list[RoofBlock]
    notes: list[str]
    warnings: list[str]
    decisions: list[dict[str, Any]]
    transcript: list[dict[str, Any]]
    api_calls: int
    filled_pct: float = 0.0
    model: str = MODEL
    usage: dict[str, int] = field(default_factory=dict)


def _r(o: Any, nd: int = 3) -> Any:
    """Round floats in nested results so the model copies short, exact numbers."""
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


# ----------------------------------------------------------------------------- evidence tables
def solar_evidence_rows(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact table rows for the prompt (Solar segments in the model frame)."""
    return [_r({"id": e["id"], "pitch_rise": e["pitch_rise"], "azimuth_deg": e["azimuth_deg"],
                "ground_area_sqft": e["ground_area_sqft"], "bbox_ft": e["bbox_ft"], "center_ft": e["center_ft"],
                "inside_footprint": e["inside_footprint"], "dist_to_footprint_ft": e["dist_to_footprint_ft"],
                "form_hint": e["form_hint"]}, 2) for e in evidence]


def lidar_evidence_rows(bs: BlockSet) -> list[dict[str, Any]]:
    """Compact table rows for the prompt (LiDAR surface blocks)."""
    nb: dict[str, list[dict[str, Any]]] = {}
    for b in bs.borders:
        nb.setdefault(b["a"], []).append({"id": b["b"], "length_ft": b["length_ft"], "step_ft": b["step_ft"]})
        nb.setdefault(b["b"], []).append({"id": b["a"], "length_ft": b["length_ft"], "step_ft": -b["step_ft"]})
    rows = []
    for b in bs.blocks:
        p = b.poly
        rows.append(_r({"id": b.id, "kind": b.kind, "pitch_rise": b.pitch_rise, "azimuth_deg": b.aspect_deg,
                        "ground_area_sqft": b.plan_area_sqft, "mean_z_ft": b.mean_z_ft,
                        "bbox_ft": list(p.bounds), "center_ft": [p.centroid.x, p.centroid.y],
                        "inside_footprint": bool(bs.footprint.contains(p.centroid)),
                        "form_hint": "flat" if b.kind == "flat" else "sloped",
                        "neighbours": nb.get(b.id, [])}, 2))
    return rows


# ----------------------------------------------------------------------------- tool workspace
class Workspace:
    """Server-side state behind the tools: polygon registry and the set of citable numbers."""

    def __init__(self, footprint_ft: list[tuple[float, float]], rows: list[dict[str, Any]],
                 segment_polys: dict[str, Polygon]) -> None:
        self.footprint = [tuple(p) for p in footprint_ft]
        self.polys: dict[str, list[tuple[float, float]]] = {"footprint": self.footprint}
        self.rows = {r["id"]: r for r in rows}
        self.segment_polys = segment_polys
        self.allowed: list[float] = [0.0] + _numbers(rows)
        self._n = 0

    def _new(self, ring: list[tuple[float, float]]) -> str:
        self._n += 1
        pid = f"p{self._n}"
        self.polys[pid] = ring_of(Polygon(ring), 0.0)  # always CCW so edge indices match what `measure` shows
        return pid

    def _poly(self, pid: str) -> list[tuple[float, float]]:
        if pid not in self.polys:
            raise KeyError(f"unknown polygon_id {pid!r}; known: {sorted(self.polys)}")
        return self.polys[pid]

    def _seg(self, ids: list[str]) -> list[dict[str, Any]]:
        missing = [i for i in ids if i not in self.rows]
        if missing:
            raise KeyError(f"unknown segment ids {missing}; known: {sorted(self.rows)}")
        return [self.rows[i] for i in ids]

    # --- tools
    def measure(self, polygon_id: str) -> dict[str, Any]:
        m = measure(self._poly(polygon_id))
        return {"polygon_id": polygon_id, "area_sqft": m["area_sqft"], "perimeter_ft": m["perimeter_ft"],
                "bounds": list(m["bounds"]), "min_rotated_rect_ft": m["min_rotated_rect_ft"],
                "edges": [{"index": e["index"], "from": list(e["from"]), "to": list(e["to"]),
                           "length_ft": e["length_ft"], "outward_bearing_deg": e["outward_bearing_deg"]}
                          for e in m["edges"]]}

    def propose_split(self, polygon_id: str, line_ft: list[list[float]]) -> dict[str, Any]:
        parts = split_footprint(self._poly(polygon_id), line_ft)
        out = []
        for part in parts:
            pid = self._new(part["polygon"])
            out.append({"polygon_id": pid, "area_sqft": part["area_sqft"],
                        "bounds": list(Polygon(part["polygon"]).bounds)})
        return {"parts": out}

    def region_from_segments(self, segment_ids: list[str]) -> dict[str, Any]:
        rows = self._seg(segment_ids)
        fp = Polygon(self.footprint)
        shapes = []
        for r in rows:
            sp = self.segment_polys.get(r["id"]) or box(*r["bbox_ft"])
            shapes.append(sp if not r.get("inside_footprint", True) and r.get("form_hint") == "sloped"
                          else sp.intersection(fp))
        union = unary_union([s for s in shapes if not s.is_empty]).buffer(0)
        parts = [p for p in polygons_of(union) if p.area > 1.0]
        ground = sum(r["ground_area_sqft"] for r in rows)
        out = []
        for p in sorted(parts, key=lambda g: -g.area):
            pid = self._new(ring_of(p.simplify(0.1), 0.0))
            out.append({"polygon_id": pid, "area_sqft": p.area, "bounds": list(p.bounds)})
        return {"parts": out, "segments_ground_area_sqft": ground}

    def rect_fit(self, polygon_id: str) -> dict[str, Any]:
        verts, short, long_, area = rect_fit(self._poly(polygon_id))
        pid = self._new(verts)
        return {"polygon_id": pid, "short_side_ft": short, "long_side_ft": long_, "area_sqft": area}

    def pitch_rise_from_segments(self, segment_ids: list[str]) -> dict[str, Any]:
        rows = [r for r in self._seg(segment_ids) if r.get("pitch_rise") is not None]
        w = sum(r["ground_area_sqft"] for r in rows) or 1.0
        mean = sum(r["pitch_rise"] * r["ground_area_sqft"] for r in rows) / w
        vals = [r["pitch_rise"] for r in rows]
        return {"pitch_rise": mean, "min": min(vals), "max": max(vals), "spread": max(vals) - min(vals),
                "n_segments": len(rows)}

    def hip_roof_edges(self, polygon_id: str, pitch_rise: float, gable_edges: list[int] | None = None
                       ) -> dict[str, Any]:
        ring = self._poly(polygon_id)
        res = hip_roof_edges(ring, pitch_rise, set(gable_edges or ()))
        t = res["totals"]
        return {"polygon_id": polygon_id, "form": "gable" if gable_edges else "hip",
                "eave_ft": t["eaves_ft"], "rake_ft": t["rakes_ft"], "ridge_ft": t["ridges_ft"],
                "hip_ft": t["hips_ft"], "valley_ft": t["valleys_ft"], "roof_area_sqft": t["facet_area_sqft"],
                "plan_area_sqft": t["plan_area_sqft"],
                "facets": [{"aspect_deg": f["aspect_deg"], "area_sqft": f["area"]} for f in res["facets"]]}

    def is_known(self, v: float) -> bool:
        return any(abs(v - a) <= NUMBER_TOL for a in self.allowed)

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = getattr(self, name, None)
        if name == "finalize" or fn is None or name.startswith("_"):
            raise KeyError(f"unknown tool {name!r}")
        res = _r(fn(**args))
        self.allowed.extend(_numbers(res))
        return res

    # --- finalize
    def finalize(self, args: dict[str, Any]) -> tuple[list[RoofBlock], list[dict[str, Any]], list[str]]:
        """Validate the decision; returns candidate blocks. Raises ValueError with a fix hint."""
        blocks: list[RoofBlock] = []
        decisions = []
        for i, b in enumerate(args.get("blocks", [])):
            ring = self._poly(b["polygon_id"])
            form = b["form"]
            n = len(ring)
            gable = [int(g) for g in b.get("gable_edges", [])]
            if signed_area(ring) < 0:  # footprint given clockwise: reverse and remap edge indices
                ring = ring[::-1]
                gable = [(n - 2 - g) % n for g in gable]
            if any(g < 0 or g >= n for g in gable):
                raise ValueError(f"block {i}: gable_edges out of range for polygon {b['polygon_id']} ({n} edges)")
            if form == "gable" and len(gable) < 2:
                raise ValueError(f"block {i}: a gable needs at least two gable_edges")
            pitch = b.get("pitch_rise")
            if form != "flat" and (pitch is None or not self.is_known(float(pitch))):
                raise ValueError(f"block {i}: pitch_rise {pitch} was not given by the evidence or a tool; "
                                 "copy it from pitch_rise_from_segments")
            aspect = b.get("aspect_deg")
            if form == "shed" and (aspect is None or not self.is_known(float(aspect))):
                raise ValueError(f"block {i}: a shed needs aspect_deg copied from the evidence azimuth")
            rb = RoofBlock(id="", form=form, polygon=list(ring),
                           pitch_rise=0.0 if form == "flat" else float(pitch), gable_edges=gable if form == "gable" else [],
                           aspect_deg=float(aspect) if aspect is not None and form == "shed" else None,
                           notes=[str(e) for e in b.get("evidence", [])], confidence=b.get("confidence", "medium"))
            geom = block_geometry(form, rb.polygon, rb.pitch_rise, rb.gable_edges, rb.aspect_deg)
            rb.ridge_azimuth_deg = ridge_azimuth(form, rb.polygon, rb.aspect_deg, geom)
            blocks.append(rb)
            decisions.append({"polygon_id": b["polygon_id"], "form": form, "pitch_rise": rb.pitch_rise,
                              "gable_edges": rb.gable_edges, "aspect_deg": rb.aspect_deg,
                              "confidence": rb.confidence, "evidence": rb.notes})
        sloped = [Polygon(r.polygon).buffer(0) for r in blocks if r.form != "flat"]
        for i in range(len(sloped)):
            for j in range(i + 1, len(sloped)):
                inter = sloped[i].intersection(sloped[j]).area
                if inter > 0.1 * min(sloped[i].area, sloped[j].area):
                    raise ValueError(f"blocks {i} and {j} overlap by {inter:.0f} sqft; split or fit them again")
        if not blocks:
            raise ValueError("finalize needs at least one block")
        return blocks, decisions, [str(w) for w in args.get("warnings", [])]


# ----------------------------------------------------------------------------- the loop
def _block_dict(b: Any) -> dict[str, Any]:
    t = getattr(b, "type", None)
    if t == "text":
        return {"type": "text", "text": b.text}
    if t == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": dict(b.input)}
    raise AgentError(f"unexpected content block type {t!r}")


def run_agent(blockset: BlockSet, evidence: list[dict[str, Any]] | None = None, *, kind: str = "solar",
              client: Any | None = None, model: str = MODEL, max_rounds: int = MAX_ROUNDS,
              imagery: dict[str, Any] | None = None, deadline: Deadline | None = None) -> AgentResult:
    """Run the tool-use loop and return completed blocks.

    ``kind`` is ``solar`` (``evidence`` = rows from ``solar.segments_to_evidence``) or
    ``lidar`` (the block set's own blocks). ``client`` is an Anthropic client (default: built
    from ``ANTHROPIC_API_KEY``); tests pass a scripted fake. Raises :class:`AgentError` when the
    loop ends without an accepted ``finalize``. With a ``deadline`` the client gets a 30 s per-call timeout and no
    SDK retries, and each round checks the time left.
    """
    if kind == "solar":
        if not evidence:
            raise AgentError("solar mode needs evidence rows")
        rows = solar_evidence_rows(evidence)
        seg_polys: dict[str, Polygon] = {}
    else:
        rows = lidar_evidence_rows(blockset)
        seg_polys = {b.id: b.poly for b in blockset.blocks}
    ws = Workspace(blockset.footprint_ft, rows, seg_polys)
    if client is None:
        client = anthropic.Anthropic(timeout=30.0, max_retries=0) if deadline else anthropic.Anthropic()

    fp_poly = blockset.footprint
    m = measure(blockset.footprint_ft)
    user = {
        "task": "Decide the roof blocks for this building.",
        "evidence_kind": "Google Solar API roof segments" if kind == "solar" else "LiDAR surface blocks",
        "imagery": imagery or {},
        "footprint": {"polygon_id": "footprint", "area_sqft": round(fp_poly.area, 1),
                      "vertices_ft": [[round(x, 2), round(y, 2)] for x, y in blockset.footprint_ft],
                      "edges": [{"index": e["index"], "length_ft": round(e["length_ft"], 2),
                                 "outward_bearing_deg": round(e["outward_bearing_deg"], 1)} for e in m["edges"]]},
        "evidence_table": rows,
    }
    messages: list[dict[str, Any]] = [{"role": "user", "content": json.dumps(user)}]
    transcript: list[dict[str, Any]] = [{"role": "user", "content": user}]
    usage = {"input_tokens": 0, "output_tokens": 0}
    api_calls = 0
    for rnd in range(1, max_rounds + 1):
        api_calls += 1
        extra: dict[str, Any] = {}
        if deadline is not None:
            deadline.check("agent")
            extra["timeout"] = deadline.timeout(30.0)
        try:
            resp = client.messages.create(model=model, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT, tools=TOOLS,
                                          messages=messages, **extra)
        except anthropic.APIError as exc:  # message is the API's own text; never the request (which holds no key)
            raise AgentError(f"Anthropic API error: {getattr(exc, 'message', type(exc).__name__)}") from None
        u = getattr(resp, "usage", None)
        if u is not None:
            usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        content = [_block_dict(b) for b in resp.content]
        messages.append({"role": "assistant", "content": content})
        calls = [b for b in content if b["type"] == "tool_use"]
        entry: dict[str, Any] = {"round": rnd, "role": "assistant",
                                 "text": " ".join(b["text"] for b in content if b["type"] == "text"),
                                 "tool_calls": [{"name": c["name"], "input": c["input"]} for c in calls],
                                 "tool_results": []}
        transcript.append(entry)
        if not calls:
            nudge = "Call finalize now with your decision."
            messages.append({"role": "user", "content": nudge})
            entry["tool_results"].append({"note": nudge})
            continue
        results = []
        accepted: tuple[list[RoofBlock], list[dict[str, Any]], list[str]] | None = None
        for c in calls:
            try:
                if c["name"] == "finalize":
                    accepted = ws.finalize(c["input"])
                    out: Any = {"status": "accepted"}
                else:
                    out = ws.call(c["name"], c["input"])
                is_err = False
            except (KeyError, ValueError, TypeError) as exc:
                out, is_err = {"error": str(exc)}, True
                accepted = None if c["name"] == "finalize" else accepted
            entry["tool_results"].append({"name": c["name"], "result": out})
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(out),
                            "is_error": is_err})
        if accepted is not None:
            blocks, decisions, warnings = accepted
            done, pct, notes = complete_tiling(blocks, blockset)
            return AgentResult(blocks=done, notes=notes, warnings=warnings, decisions=decisions,
                               transcript=transcript, api_calls=api_calls, filled_pct=pct, model=model, usage=usage)
        remaining = max_rounds - rnd
        if remaining <= 2:
            results.append({"type": "text", "text": f"{remaining} round(s) left. Call finalize now."})
        messages.append({"role": "user", "content": results})
    raise AgentError(f"the agent did not finalize within {max_rounds} rounds")


def agent_notes(result: AgentResult) -> list[str]:
    """One line per decision for the model's confidence notes."""
    out = []
    for d in result.decisions:
        ev = "; ".join(d["evidence"][:2])
        out.append(f"Agent ({result.model}): {d['form']} at {d['pitch_rise']:.2f}/12 ({d['confidence']}) {ev}".strip())
    return out

