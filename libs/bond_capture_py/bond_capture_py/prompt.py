"""The system prompt (``prompt_v1.md``, package data) and the fence around the user's text."""

from datetime import date, time
from html import escape
from importlib.resources import files

_BEGIN = "<!-- BEGIN SYSTEM PROMPT -->"
_END = "<!-- END SYSTEM PROMPT -->"
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _template() -> str:
    raw = files("bond_capture_py").joinpath("prompt_v1.md").read_text(encoding="utf-8")
    return raw.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()


def build_prompt(today: date, weekday: str | None, time_zone: str, end_of_day: time) -> str:
    """The system prompt: the text between the marker lines of ``prompt_v1.md`` with ``{{today}}``,
    ``{{weekday}}``, ``{{zone}}`` and ``{{end_of_day}}`` filled (YYYY-MM-DD, English weekday, IANA name, HH:MM).
    ``weekday`` None means the English name of ``today``."""
    fills = {
        "{{today}}": today.isoformat(),
        "{{weekday}}": weekday or _WEEKDAYS[today.weekday()],
        "{{zone}}": time_zone,
        "{{end_of_day}}": f"{end_of_day.hour:02d}:{end_of_day.minute:02d}",
    }
    prompt = _template()
    for token, value in fills.items():
        prompt = prompt.replace(token, value)
    return prompt


def fence(text: str) -> str:
    """The user message: the text HTML-escaped (& < >) and wrapped in the fence the prompt names, so the note is
    data and never instructions."""
    return f"<untrusted_text>\n{escape(text, quote=False)}\n</untrusted_text>"
