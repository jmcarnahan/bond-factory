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
from shapely.errors import ShapelyError
from shapely.geometry import Polygon

from . import config
from .agent_draft import capture_gables, remap_gables
from .agent_partition import tidy_tiling
from .agent_prompt import BLOCK_SCHEMA, SYSTEM_PROMPT, TOOLS  # noqa: F401 - re-exported
from .agent_repair import advice, repair_blocks, unbuildable
from .agent_tools import NUMBER_TOL, Workspace, _numbers, _r  # noqa: F401 - re-exported
from .classify import BlockSet, RoofBlock, complete_tiling
from .deadline import Deadline
from .pipeline_stages import PipelineError
from .skeleton import measure

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
MAX_ROUNDS = 12
MAX_TOKENS = 12000  # thinking counts inside max_tokens; 6000 left too little room for thinking plus a tool call
THINKING = {"type": "between_tools"}  # explicit, like the verifier: behaviour must not depend on a model default
# a tool may fail in these ways on bad model input; the model reads the message and retries (never a crash)
TOOL_ERRORS = (KeyError, ValueError, TypeError, AttributeError, IndexError, ArithmeticError, RuntimeError, ShapelyError)

class AgentError(RuntimeError):
    """The agent did not produce an acceptable answer."""


class AgentAuthError(PipelineError):
    """The Anthropic key was rejected (invalid, revoked, no access). A caller error like a missing key.

    Deliberately NOT an AgentError: the pipeline falls back to the rules only for genuine agent failures.
    """


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
                        "height_ft": b.height_above_ground_ft,
                        "bbox_ft": list(p.bounds), "center_ft": [p.centroid.x, p.centroid.y],
                        "inside_footprint": bool(bs.footprint.contains(p.centroid)),
                        "form_hint": "flat" if b.kind == "flat" else "sloped",
                        "neighbours": nb.get(b.id, [])}, 2))
    return rows


# ----------------------------------------------------------------------------- the loop
def _tool_error_text(exc: Exception) -> str:
    """What the model reads when a tool call fails: the message for our own checks, the class for library errors."""
    if isinstance(exc, ShapelyError | AttributeError | IndexError | ArithmeticError | RuntimeError):
        return (f"{type(exc).__name__}: the tool could not use that input ({str(exc)[:160]}); check the polygon ids, "
                "numbers and JSON types in your call, or call rect_fit first")
    return str(exc)


def _block_dict(b: Any) -> dict[str, Any]:
    """An assistant content block as a plain dict, to echo back in the next request.

    Every block is kept as received: a thinking block needs its signature and a redacted_thinking block its data,
    in the original order, or the API rejects the next turn. Unknown block types are kept, never rejected.
    """
    if hasattr(b, "model_dump"):  # a real SDK block
        return b.model_dump(exclude_none=True)
    t = getattr(b, "type", None)
    if t == "text":
        return {"type": "text", "text": b.text}
    if t == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": dict(b.input)}
    if isinstance(b, dict):
        return dict(b)
    return {k: v for k, v in vars(b).items() if v is not None}  # a plain object (tests): keep what it carries


def _thinking_of(content: list[dict[str, Any]]) -> dict[str, Any]:
    """Transcript fields for the thinking blocks of one turn (text of ``thinking``, a count of redacted ones)."""
    out: dict[str, Any] = {}
    texts = [str(b.get("thinking", "")) for b in content if b.get("type") == "thinking"]
    if texts:
        out["thinking"] = texts
    redacted = sum(1 for b in content if b.get("type") == "redacted_thinking")
    if redacted:
        out["redacted_thinking_blocks"] = redacted
    return out


def _check_stop(resp: Any) -> None:
    """A turn cut off by the token limit or refused is a clear AgentError, not a silent malformed turn."""
    stop = getattr(resp, "stop_reason", None)
    if stop == "max_tokens":
        raise AgentError(f"the model ran out of output tokens (max_tokens={MAX_TOKENS}, thinking included) "
                         "before it finished a turn")
    if stop == "refusal":
        raise AgentError("the model declined to answer")


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
    ws = Workspace(blockset.footprint_ft, rows, seg_polys, blockset if kind == "lidar" else None)
    if client is None:
        client = (anthropic.Anthropic(api_key=config.anthropic_key(), timeout=30.0, max_retries=0) if deadline
                  else anthropic.Anthropic(api_key=config.anthropic_key()))

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
    # the evidence is resent every round: one cache breakpoint after it makes rounds 2.. read it from the cache
    messages: list[dict[str, Any]] = [{"role": "user", "content": [
        {"type": "text", "text": json.dumps(user), "cache_control": {"type": "ephemeral"}}]}]
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
                                          messages=messages, thinking=THINKING, **extra)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise AgentAuthError("The Anthropic API key was rejected (invalid, revoked or without access); "
                                 "check ANTHROPIC_API_KEY or the anthropic_api_key argument.") from None
        except anthropic.APIError as exc:  # message is the API's own text; never the request (which holds no key)
            raise AgentError(f"Anthropic API error: {getattr(exc, 'message', type(exc).__name__)}") from None
        u = getattr(resp, "usage", None)
        if u is not None:
            usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
            for k in ("cache_creation_input_tokens", "cache_read_input_tokens"):  # only when the API reports them
                n = getattr(u, k, 0)
                if isinstance(n, int) and n:
                    usage[k] = usage.get(k, 0) + n
        _check_stop(resp)
        content = [_block_dict(b) for b in resp.content]
        messages.append({"role": "assistant", "content": content})
        calls = [b for b in content if b["type"] == "tool_use"]
        entry: dict[str, Any] = {"round": rnd, "role": "assistant",
                                 "text": " ".join(str(b.get("text", "")) for b in content if b["type"] == "text"),
                                 **_thinking_of(content),
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
            except TOOL_ERRORS as exc:
                out, is_err = {"error": _tool_error_text(exc)}, True
                accepted = None if c["name"] == "finalize" else accepted
            entry["tool_results"].append({"name": c["name"], "result": out})
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(out),
                            "is_error": is_err})
        if accepted is not None:
            blocks, decisions, warnings = accepted
            pid_of = {id(rb): d["polygon_id"] for rb, d in zip(blocks, decisions, strict=True)}
            captured = capture_gables(blocks)
            done, pct, notes = complete_tiling(blocks, blockset)
            remap_gables(done, captured)  # tiling re-rings the blocks: keep the gable ends the agent chose
            notes = [*notes, *tidy_tiling(done, blockset)]  # one partition: higher block wins, outlines simple
            bad = unbuildable(done)  # the builder's own check, on the blocks as they will be built
            if bad and rnd < max_rounds:  # tell the agent while it can still act on it
                text = advice([(rb, why, pid_of.get(id(rb), "?")) for rb, why in bad])
                for res_row, tr in zip(results, entry["tool_results"], strict=True):
                    if tr.get("name") == "finalize":
                        tr["result"] = {"error": text}
                        res_row.update(content=json.dumps({"error": text}), is_error=True)
                messages.append({"role": "user", "content": results})
                continue
            if bad:  # out of rounds: repair block by block, then the pipeline's own fallbacks answer
                repaired = repair_blocks(done)
                notes = [*notes, *repaired]
                warnings = [*warnings, *repaired]
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

