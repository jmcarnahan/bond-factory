"""The LLM step of the verifier: a bounded tool-use loop that must end in ``finalize_verdict``.

The prompt carries only service-generated numbers (edge table, totals): no address, no OSM tags. Failures
(API error, deadline, token cap, no finalize) do not raise: they come back in ``LoopResult.error`` and the
caller keeps the deterministic result as ``unverified``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .deadline import Deadline, DeadlineExceeded
from .verify_tools import TOOLS, Workspace

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 2000
TOKEN_CAP = 40000
MAX_TABLE_ROWS = 120

SYSTEM_PROMPT = """You are an adversarial reviewer of a roof measurement. You receive a table of roof edges \
(feet) and the totals computed from them. Look for measurement artefacts: runs of tiny, nearly collinear \
segments of one type that should be one line, and totals that do not add up. You may call merge_collinear \
(angle_tol_deg <= 5, min_len_ft <= 3) to fix runs, and recompute_totals to see the effect.

RULES
1. Every number you quote in notes or adjustments must come from a tool result. Never estimate or compute one.
2. Do not invent features. Say only what the tables show.
3. Finish by calling finalize_verdict with verdict pass (nothing wrong), adjusted (totals changed by merges) \
or fail (a total is wrong by more than a few percent). The harness recomputes the verdict from the totals.
4. Be efficient: you have at most 6 rounds, finish in about 3."""


@dataclass
class LoopResult:
    final: dict[str, Any] | None = None
    rounds: int = 0
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    error: str | None = None
    transcript: list[dict[str, Any]] = field(default_factory=list)


def request_kwargs(messages: list[dict[str, Any]], deadline: Deadline, *, max_tokens: int = MAX_TOKENS,
                   model: str = MODEL, system: str = SYSTEM_PROMPT) -> dict[str, Any]:
    """The exact ``messages.create`` kwargs (forced tool_choice is a 400 on this model; no budget_tokens)."""
    return {"model": model, "max_tokens": max_tokens, "system": system, "tools": TOOLS,
            "tool_choice": {"type": "auto"}, "thinking": {"type": "between_tools"},
            "output_config": {"effort": "low"}, "messages": messages, "timeout": deadline.timeout(30)}


def _user_prompt(ws: Workspace) -> str:
    table = ws.call("measure_edges", {})
    rows = table["edges"]
    if len(rows) > MAX_TABLE_ROWS:  # most suspicious first: short or kinked edges
        rows = sorted(rows, key=lambda r: (r["turning_deg_to_next"] is None, r["length_ft"]))[:MAX_TABLE_ROWS]
        table = {**table, "edges": rows, "note": f"first {MAX_TABLE_ROWS} of {table['n_edges']} edges shown"}
    totals = ws.call("recompute_totals", {})["totals"]
    return json.dumps({"task": "Review this roof measurement.", "edges": table, "totals": totals})


def _block_dict(b: Any) -> dict[str, Any]:
    if hasattr(b, "model_dump"):  # real SDK block: keep thinking blocks intact for the next round
        return b.model_dump(exclude_none=True)
    if b.type == "text":
        return {"type": "text", "text": b.text}
    return {"type": "tool_use", "id": b.id, "name": b.name, "input": dict(b.input)}


def _reason(exc: Exception) -> str:
    if isinstance(exc, DeadlineExceeded):
        return "verifier ran out of time"
    if isinstance(exc, anthropic.APIError):
        status = getattr(exc, "status_code", None)
        return f"Anthropic API error ({type(exc).__name__}{f' {status}' if status else ''})"
    return f"verifier error ({type(exc).__name__})"


def run_loop(ws: Workspace, client: Any, deadline: Deadline, *, max_rounds: int = 6,
             max_tokens: int = MAX_TOKENS, token_cap: int = TOKEN_CAP) -> LoopResult:
    res = LoopResult()
    try:
        messages: list[dict[str, Any]] = [{"role": "user", "content": _user_prompt(ws)}]
        for rnd in range(1, max_rounds + 1):
            deadline.check("verify")
            res.rounds = rnd
            resp = client.messages.create(**request_kwargs(messages, deadline, max_tokens=max_tokens))
            u = getattr(resp, "usage", None)
            res.usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            res.usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
            content = [_block_dict(b) for b in resp.content]
            messages.append({"role": "assistant", "content": content})
            calls = [b for b in content if b["type"] == "tool_use"]
            entry: dict[str, Any] = {"round": rnd, "tool_calls": [{"name": c["name"], "input": c["input"]} for c in calls],
                                     "tool_results": []}
            res.transcript.append(entry)
            last_cost = (getattr(u, "input_tokens", 0) or 0) + (getattr(u, "output_tokens", 0) or 0)
            over = sum(res.usage.values()) + last_cost > token_cap  # would the next call cross the cap?
            if not calls:
                if over:
                    res.error = "verifier stopped at the token cap"
                    return res
                messages.append({"role": "user", "content": "Call finalize_verdict now."})
                continue
            results = []
            for c in calls:
                try:
                    if c["name"] == "finalize_verdict":
                        out = ws.finalize(c["input"])
                    else:
                        out = ws.call(c["name"], c["input"])
                except (KeyError, ValueError, TypeError) as exc:
                    out = {"error": str(exc)}
                entry["tool_results"].append({"name": c["name"], "result": out})
                results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(out),
                                "is_error": "error" in out})
            if ws.final is not None:
                res.final = ws.final
                return res
            if over:
                res.error = "verifier stopped at the token cap"
                return res
            if max_rounds - rnd <= 2:
                results.append({"type": "text", "text": f"{max_rounds - rnd} round(s) left. Call finalize_verdict."})
            messages.append({"role": "user", "content": results})
        res.error = f"verifier did not finalize within {max_rounds} rounds"
    except Exception as exc:  # noqa: BLE001 - D1: the verifier never fails a job
        res.error = _reason(exc)
        log.warning("verifier loop stopped: %s", res.error)
    return res
