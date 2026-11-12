"""``parse_capture``: one note in, candidates out. Creates nothing; never logs the text."""

import logging
import math
from collections.abc import Sequence
from datetime import date, time

from bond_capture_py.candidates import CaptureResult, TaskCandidate
from bond_capture_py.errors import CaptureError, LlmInvalid
from bond_capture_py.fallback import degraded_draft
from bond_capture_py.prompt import build_prompt, fence
from bond_capture_py.protocols import CaptureGuard, EntityResolver, LlmClient
from bond_capture_py.schema import DEFAULT_KINDS, MAX_TEXT, check_kinds, model_schema
from bond_capture_py.textclean import clean_text
from bond_capture_py.validate import to_candidates

log = logging.getLogger("bond_capture_py")  # only lengths, counts and exception type names are ever logged
MAX_CANDIDATES_PER_LINK = 5


def _degraded(text: str, today: date, reason: str, rich: bool = False) -> CaptureResult:
    d = degraded_draft(text, today)
    draft = TaskCandidate(title=d["title"], due_date=d["due_date"], due_time=d["due_time"],
                          due_defaulted=d["due_defaulted"], priority=d["priority"], confidence=d["confidence"],
                          flags=tuple(d["flags"]), degraded=True)
    log.info("capture degraded reason=%s text_len=%d", reason, len(text))
    return CaptureResult(items=(draft,), degraded=True, reason=reason, rich=rich)


def _row(r: dict, rich: bool) -> dict:
    row = {"id": str(r["id"]), "label": str(r.get("label", ""))}
    if rich:  # extra scalar keys ride along (a rank, a type); id and label are always the resolver's own
        row.update({k: v for k, v in r.items() if k not in row and isinstance(k, str)
                    and (v is None or isinstance(v, (str, int, float, bool)))
                    and not (isinstance(v, float) and not math.isfinite(v))})  # NaN and inf are not JSON
    return row


def _resolver(resolver: EntityResolver | None, user_id: str, rich: bool = False):
    def resolve(name: str, kind: str) -> list:
        if resolver is None:
            return []
        try:
            found = resolver.resolve(user_id, name, kind)
        except Exception as exc:  # noqa: BLE001 - a broken lookup must not lose the capture
            log.warning("capture resolver failed type=%s", type(exc).__name__)
            return []
        rows = [_row(r, rich) for r in found or [] if isinstance(r, dict) and r.get("id") is not None]
        return rows[:MAX_CANDIDATES_PER_LINK]

    return resolve


def parse_capture(text: str, *, user_id: str, today: date, time_zone: str, end_of_day: time,
                  llm: LlmClient | None, resolver: EntityResolver | None = None,
                  guard: CaptureGuard | None = None, timeout_s: float = 20.0, rich: bool = False,
                  resolver_kinds: Sequence[str] = DEFAULT_KINDS) -> CaptureResult:
    """Order: validate (``text_required``, ``text_too_long`` over ``MAX_TEXT``); ``guard.check`` (may raise
    ``CaptureDenied``); ``llm.complete_json`` with ``build_prompt`` and ``fence`` against ``MODEL_SCHEMA``;
    validate the answer locally (see ``validate.py``: shape, kinds, every date through ``date.fromisoformat``,
    limits); map items to candidates and resolve each link's name through ``resolver`` (contact ids never go
    to the model). ``llm`` None, ``LlmUnavailable`` or any other exception gives a degraded draft with reason
    ``model_unavailable``; ``LlmInvalid`` or an unusable answer gives one with reason ``invalid_output``.

    ``rich=True`` uses ``prompt_v2.md`` and the rich schema: events gain ``location``, ``notes``,
    ``duration_minutes`` (their ``end`` is start plus the length when no end was stated) and ``attendees``
    (names, never resolved); tasks gain ``notes``; the wire carries those keys and resolver rows keep extra
    scalar keys. ``resolver_kinds`` lists what a link may point at; each link's name is resolved through
    ``resolver.resolve(user_id, name, kind)`` with its own kind. Defaults give today's behaviour."""
    kinds = check_kinds(resolver_kinds)
    text = (text or "").strip()
    if not clean_text(text, MAX_TEXT + 1):  # nothing but spaces, controls or bidi marks is no text
        raise CaptureError("text_required")
    if len(text) > MAX_TEXT:
        raise CaptureError("text_too_long")
    if guard is not None:
        guard.check(user_id, text)
    if llm is None:
        return _degraded(text, today, "model_unavailable", rich)
    system = build_prompt(today, None, time_zone, end_of_day, rich=rich, kinds=kinds)
    try:
        answer = llm.complete_json(system, fence(text), model_schema(rich, kinds), timeout_s)
    except LlmInvalid:
        return _degraded(text, today, "invalid_output", rich)
    except Exception as exc:  # noqa: BLE001 - any vendor failure degrades; never log the message (may quote the prompt)
        log.warning("capture model failed type=%s", type(exc).__name__)
        return _degraded(text, today, "model_unavailable", rich)
    try:
        items, dropped = to_candidates(answer, today, _resolver(resolver, user_id, rich), rich=rich, kinds=kinds)
    except Exception:  # noqa: BLE001 - LlmInvalid, or anything a hostile answer provokes
        return _degraded(text, today, "invalid_output", rich)
    log.info("capture ok text_len=%d items=%d dropped=%d", len(text), len(items), dropped)
    return CaptureResult(items=items, dropped=dropped, rich=rich)
