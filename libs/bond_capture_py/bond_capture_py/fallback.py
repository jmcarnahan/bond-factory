"""The degraded fallback: model unavailable gives ONE task draft, never an event. Standard library only."""

from datetime import date


def degraded_draft(text: str, today: date) -> dict:
    """A flat model-shaped item (``MODEL_SCHEMA`` keys plus ``degraded: true``, ``confidence`` 0.2) with the whole
    text as title (200 characters), a date from tomorrow / today / "in N days" / a weekday name, a time from
    "at 3pm" / "noon", priority from "urgent" / "low priority", and ``due_defaulted`` when no date was found."""
    raise NotImplementedError("fallback.degraded_draft is not implemented yet")
