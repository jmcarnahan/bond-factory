"""The system prompt (``prompt_v1.md``, package data) and the fence around the user's text."""

from datetime import date, time


def build_prompt(today: date, weekday: str, time_zone: str, end_of_day: time) -> str:
    """The system prompt: the text between the marker lines of ``prompt_v1.md`` with ``{{today}}``,
    ``{{weekday}}``, ``{{zone}}`` and ``{{end_of_day}}`` filled (YYYY-MM-DD, English weekday, IANA name, HH:MM)."""
    raise NotImplementedError("prompt.build_prompt is not implemented yet")


def fence(text: str) -> str:
    """The user message: the text HTML-escaped (& < >) and wrapped in the fence the prompt names, so the note is
    data and never instructions."""
    raise NotImplementedError("prompt.fence is not implemented yet")
