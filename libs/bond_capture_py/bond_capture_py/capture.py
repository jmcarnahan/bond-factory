"""``parse_capture``: one note in, candidates out. Creates nothing; never logs the text."""

from datetime import date, time

from bond_capture_py.candidates import CaptureResult
from bond_capture_py.protocols import CaptureGuard, EntityResolver, LlmClient


def parse_capture(text: str, *, user_id: str, today: date, time_zone: str, end_of_day: time,
                  llm: LlmClient | None, resolver: EntityResolver | None = None,
                  guard: CaptureGuard | None = None, timeout_s: float = 20.0) -> CaptureResult:
    """Order: validate (``text_required``, ``text_too_long`` over ``MAX_TEXT``); ``guard.check`` (may raise
    ``CaptureDenied``); ``llm.complete_json`` with ``build_prompt`` and ``fence`` against ``MODEL_SCHEMA``;
    validate the answer (the schema pattern admits "2026-13-45", so every ``date`` and ``end_date`` is also
    checked with ``date.fromisoformat``; a bad date makes the answer ``invalid_output`` and the fallback runs);
    map items to candidates (a task's date is ``due_date``; ``due_time`` only when stated;
    an event with a date and no time is all-day; resolve each link's name through ``resolver``; flag
    ``low_confidence`` under 0.5). ``llm`` None, ``LlmUnavailable`` or a schema failure (``LlmInvalid``) gives
    ``CaptureResult((degraded_candidate,), True, reason)`` built from ``degraded_draft``."""
    raise NotImplementedError("capture.parse_capture is not implemented yet")
