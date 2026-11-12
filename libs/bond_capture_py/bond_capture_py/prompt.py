"""The system prompts (``prompt_v1.md``, and ``prompt_v2.md`` for rich mode; package data) and the fence."""

from collections.abc import Sequence
from datetime import date, time
from html import escape
from importlib.resources import files

from bond_capture_py.schema import DEFAULT_KINDS, check_kinds

_BEGIN = "<!-- BEGIN SYSTEM PROMPT -->"
_END = "<!-- END SYSTEM PROMPT -->"
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _template(rich: bool = False) -> str:
    raw = files("bond_capture_py").joinpath("prompt_v2.md" if rich else "prompt_v1.md").read_text(encoding="utf-8")
    return raw.split(_BEGIN, 1)[1].split(_END, 1)[0].strip()


def build_prompt(today: date, weekday: str | None, time_zone: str, end_of_day: time, *, rich: bool = False,
                 kinds: Sequence[str] = DEFAULT_KINDS) -> str:
    """The system prompt: the text between the marker lines of ``prompt_v1.md`` with ``{{today}}``,
    ``{{weekday}}``, ``{{zone}}`` and ``{{end_of_day}}`` filled (YYYY-MM-DD, English weekday, IANA name, HH:MM).
    ``weekday`` None means the English name of ``today``. ``rich`` uses ``prompt_v2.md``. ``kinds`` (see
    ``resolver_kinds``): when it is not just ``("contact",)`` one paragraph names the allowed link kinds."""
    kinds = check_kinds(kinds)
    fills = {
        "{{today}}": today.isoformat(),
        "{{weekday}}": weekday or _WEEKDAYS[today.weekday()],
        "{{zone}}": time_zone,
        "{{end_of_day}}": f"{end_of_day.hour:02d}:{end_of_day.minute:02d}",
    }
    prompt = _template(rich)
    for token, value in fills.items():
        prompt = prompt.replace(token, value)
    if kinds != DEFAULT_KINDS:
        names = ", ".join(f'"{k}"' for k in kinds)
        example = "contact" if "contact" in kinds else kinds[0]  # examples keep "contact" when the app lists it
        prompt = prompt.replace('"kind": "contact"', f'"kind": one of {names}').replace(
            '"kind":"contact"', f'"kind":"{example}"')
        prompt += (f"\n\nLink kinds: a link's kind is one of {names}. Use the kind that names what the link is; "
                   f'use "{kinds[0]}" when unsure. Names only; never ids.')
    return prompt


def fence(text: str) -> str:
    """The user message: the text HTML-escaped (& < >) and wrapped in the fence the prompt names, so the note is
    data and never instructions."""
    return f"<untrusted_text>\n{escape(text, quote=False)}\n</untrusted_text>"
