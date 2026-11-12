"""Rich mode: the four extra fields of a model item, checked locally, and the event end from a duration."""

from datetime import date, datetime, time, timedelta

from bond_capture_py.errors import LlmInvalid
from bond_capture_py.schema import ATTENDEE_CAP, LOCATION_CAP, MAX_ATTENDEES, MAX_DURATION, NOTES_CAP
from bond_capture_py.textclean import clean_text

RICH_KEYS = ("location", "notes", "duration_minutes", "attendees")


def _bad(why: str) -> LlmInvalid:
    return LlmInvalid(message=why)


def _text_or_none(value, cap: int) -> str | None:
    """A model slip in an optional text field (a number, a list) is no text, and the item is kept."""
    if not isinstance(value, str):
        return None
    return clean_text(value, cap) or None


def _duration(value) -> int | None:
    """A whole positive number of minutes within range, as an int, a whole float or a numeric string; else None."""
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float):
        if not value.is_integer():  # NaN, inf and 30.5 all fail here
            return None
        value = int(value)
    return value if 1 <= value <= MAX_DURATION else None  # an impossible length is no length


def _names(value) -> tuple[str, ...]:
    """Attendee names as written. A name that holds ``@`` or ``://`` is an address or a link, not a name: dropped."""
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for name in value[:MAX_ATTENDEES * 10]:  # a bounded look: a hostile answer cannot make this slow
        if len(out) == MAX_ATTENDEES:
            break
        if not isinstance(name, str) or "@" in name or "://" in name:
            continue
        cleaned = clean_text(name, ATTENDEE_CAP)
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            out.append(cleaned)
    return tuple(out)


def rich_fields(raw: dict) -> dict:
    """The validated rich fields of a raw item. ``LlmInvalid`` when a key is missing; a wrong type in an optional field
    is coerced to null (empty for attendees) and the item is kept."""
    if any(key not in raw for key in RICH_KEYS):
        raise _bad("bad item shape")
    return {"location": _text_or_none(raw["location"], LOCATION_CAP), "notes": _text_or_none(raw["notes"], NOTES_CAP),
            "duration_minutes": _duration(raw["duration_minutes"]), "attendees": _names(raw["attendees"])}


def end_from_duration(start: date, start_time: str | None, minutes: int | None) -> tuple[str, str] | None:
    """``(end_date, end_time)`` for a timed event of ``minutes``; None when either is unknown (an all-day event
    has no clock end)."""
    if start_time is None or minutes is None:
        return None
    hour, minute = int(start_time[:2]), int(start_time[3:])
    end = datetime.combine(start, time(hour, minute)) + timedelta(minutes=minutes)
    return end.date().isoformat(), end.strftime("%H:%M")


def span_minutes(start: date, start_time: str | None, end: date | None, end_time: str | None) -> int | None:
    """Minutes from the start to an explicit end of a timed event; None when either clock time or the end date is
    missing, or the span is zero, negative or over ``MAX_DURATION``."""
    if start_time is None or end_time is None or end is None:
        return None
    begin = datetime.combine(start, time(int(start_time[:2]), int(start_time[3:])))
    finish = datetime.combine(end, time(int(end_time[:2]), int(end_time[3:])))
    minutes = int((finish - begin).total_seconds() // 60)
    return minutes if 1 <= minutes <= MAX_DURATION else None
