"""The verifier seam (contract section 3.3): deterministic merge always, LLM review when a client or key exists.

The verdict is computed from the totals delta, never taken from the model. The verifier never fails a job:
any problem gives verdict ``unverified`` with the deterministic result kept.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from . import config
from .deadline import Deadline
from .envelope import totals_from_model
from .verify_llm import MODEL, run_loop
from .verify_merge import merge_collinear
from .verify_tools import Workspace, checker_for

MIN_LLM_SECONDS = 5.0
WALL_CLOCK = 60.0


@dataclass
class VerifyResult:
    model: dict[str, Any]
    verification: dict[str, Any]
    transcript: list[dict[str, Any]] = field(default_factory=list)  # the LLM rounds, [] when it did not run


def _merge_note(a: dict[str, Any]) -> str:
    return (f"Merged {len(a['edge_ids'])} {a['edge_type']} segments into one {a['length_after_ft']} ft line "
            f"(was {a['length_before_ft']} ft).")


def verify(model: dict[str, Any], *, client: Any = None, api_key: str | None = None,
           deadline: Deadline | None = None, angle_tol_deg: float = 3.0, min_len_ft: float = 2.0) -> VerifyResult:
    src = copy.deepcopy(model)
    original = totals_from_model(src)
    notes: list[str] = []
    try:  # chain by chain: a chain that breaks validate is skipped, the others still merge
        merged, adjustments = merge_collinear(src, angle_tol_deg, min_len_ft, checker_for(src))
    except Exception as exc:  # noqa: BLE001 - D1: a malformed edge must not fail the job
        notes.append(f"Deterministic merge skipped ({type(exc).__name__}).")
        merged, adjustments = copy.deepcopy(src), []
    notes += [_merge_note(a) for a in adjustments]
    budget = Deadline.after(min(WALL_CLOCK, deadline.remaining())) if deadline else Deadline.after(WALL_CLOCK)
    ws = Workspace(merged, adjustments, original, angle_tol_deg, min_len_ft, src["totals"]["lengths_ft"])
    llm_model: str | None = None
    rounds, usage = 0, {"input_tokens": 0, "output_tokens": 0}
    transcript: list[dict[str, Any]] = []
    verdict, reason = "unverified", None
    key = api_key or config.anthropic_key()
    if client is None and key:
        import anthropic
        client = anthropic.Anthropic(max_retries=0, api_key=key)  # the deadline owns retries
    if client is None:
        reason = "no ANTHROPIC_API_KEY: only the deterministic merge ran"
    elif budget.remaining() <= MIN_LLM_SECONDS:
        reason = "not enough time left for the LLM review"
    else:
        llm_model = MODEL
        res = run_loop(ws, client, budget, max_rounds=6)
        rounds, usage, transcript = res.rounds, res.usage, res.transcript
        if res.final is not None:
            verdict = res.final["verdict"]
            notes += res.final["notes"]
        else:
            reason = res.error or "verifier did not finalize"
    final, kept = ws.model, ws.adjustments
    if ws.check is not None:  # D1: never hand back a model that no longer validates
        try:
            ws.check(final)
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Review changes discarded, model did not validate ({type(exc).__name__}).")
            final, kept = merged, adjustments
            ws.model = final
            if verdict != "unverified":
                verdict = ws.verdict()
    current = totals_from_model(final)
    computed = ws.verdict()
    if reason:
        extra = ""
        if verdict == "unverified" and computed != "pass":
            area = (current["area_sqft"] - original["area_sqft"]) / original["area_sqft"] * 100 if original["area_sqft"] else 0.0
            what = f"area {area:.1f}%" if abs(area) >= 0.05 else "edge totals"
            extra = f"; deterministic merge moved {what} (would {computed})"
        notes.append(f"Unverified: {reason}{extra}.")
    return VerifyResult(model=final, transcript=transcript, verification={
        "verdict": verdict, "notes": notes, "adjustments": kept, "original_totals": original,
        "model": llm_model, "rounds": rounds, "usage": usage})
