"""Local validation of the model's answer and its mapping to candidates. Never logs; never trusts the vendor."""

import math
import re
from collections.abc import Callable
from datetime import date, timedelta

from bond_capture_py.candidates import (
    FLAG_LOW_CONFIDENCE,
    LOW_CONFIDENCE,
    EventCandidate,
    LinkCandidate,
    TaskCandidate,
)
from bond_capture_py.errors import LlmInvalid
from bond_capture_py.rich import end_from_duration, rich_fields, span_minutes
from bond_capture_py.schema import DEFAULT_KINDS, MAX_ITEMS, MAX_LINKS
from bond_capture_py.textclean import clean_text

FLAG_MISSED = "missed"  # an event that started before today; never "overdue" (that word is for tasks)
TITLE_CAP = 255
LINK_TEXT_CAP = 80
HORIZON_DAYS = 5 * 365 + 1  # a date further out than this is a model slip
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)  # always fullmatch: "$" would pass a trailing newline
_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d", re.ASCII)
_KEYS = ("kind", "title", "date", "time", "due_defaulted", "priority", "all_day", "end_date", "end_time", "links",
         "confidence")

Resolve = Callable[[str, str], list]  # (name, kind) -> rows


def _bad(why: str) -> LlmInvalid:
    return LlmInvalid(message=why)


def _date_or_none(value) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise _bad("bad date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise _bad("bad date") from None


def _time_or_none(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _TIME.fullmatch(value):
        raise _bad("bad time")
    return value


def _flag(value, what: str) -> bool:
    if not isinstance(value, bool):
        raise _bad(what)
    return value


def _priority(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # 2.0 is 2
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 3:
        raise _bad("bad priority")
    return value


def _confidence(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad("bad confidence")
    try:
        number = float(value)  # an int such as 10**400 overflows here
    except OverflowError:
        raise _bad("bad confidence") from None
    if not math.isfinite(number):
        raise _bad("bad confidence")
    return min(1.0, max(0.0, number))


def _link_texts(value, kinds: tuple[str, ...]) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        raise _bad("bad links")
    texts = []
    for link in value[:MAX_LINKS]:
        if not isinstance(link, dict) or not isinstance(link.get("text"), str):
            raise _bad("bad link")
        text = clean_text(link["text"], LINK_TEXT_CAP)
        if text:
            kind = link.get("kind", kinds[0])  # no kind at all means the first
            if len(kinds) == 1:
                kind = kinds[0]  # one kind (the default): whatever the model called it, it is that kind
            if isinstance(kind, str) and kind in kinds:  # several kinds: one the app does not resolve is dropped
                texts.append((text, kind))
    return texts


def _check_item(raw, today: date, kinds: tuple[str, ...], rich: bool) -> dict | None:
    """The validated item, None when the item alone is dropped, ``LlmInvalid`` when the answer is unusable."""
    if not isinstance(raw, dict) or any(key not in raw for key in _KEYS):
        raise _bad("bad item shape")
    if raw["kind"] not in ("task", "event"):
        raise _bad("bad kind")
    if not isinstance(raw["title"], str):
        raise _bad("bad title")
    item = {
        "kind": raw["kind"],
        "date": _date_or_none(raw["date"]),
        "time": _time_or_none(raw["time"]),
        "due_defaulted": _flag(raw["due_defaulted"], "bad due_defaulted"),
        "priority": _priority(raw["priority"]),
        "all_day": _flag(raw["all_day"], "bad all_day"),
        "end_date": _date_or_none(raw["end_date"]),
        "end_time": _time_or_none(raw["end_time"]),
        "link_texts": _link_texts(raw["links"], kinds),
        "confidence": _confidence(raw["confidence"]),
        "title": clean_text(raw["title"], TITLE_CAP),
    }
    if not item["title"]:
        return None
    if rich:
        item.update(rich_fields(raw))
    far = today + timedelta(days=HORIZON_DAYS)
    if any(d is not None and d > far for d in (item["date"], item["end_date"])):
        return None
    return item


def _task(item: dict, today: date, links: tuple) -> TaskCandidate:
    due, due_time = item["date"], item["time"]
    defaulted = item["due_defaulted"] or due is None
    if due is None or due < today:
        # A date that has passed becomes today as a default; its clock time goes too, or "yesterday 09:00"
        # would become a task that is overdue the moment it is saved.
        due, defaulted = today, True
        if item["date"] is not None:
            due_time = None
    flags = (FLAG_LOW_CONFIDENCE,) if item["confidence"] < LOW_CONFIDENCE else ()
    return TaskCandidate(title=item["title"], due_date=due.isoformat(), due_time=due_time,
                         due_defaulted=defaulted, priority=item["priority"], links=links,
                         confidence=item["confidence"], flags=flags, notes=item.get("notes"))


def _event(item: dict, today: date, links: tuple) -> EventCandidate:
    start = item["date"]
    flags = [FLAG_LOW_CONFIDENCE] if item["confidence"] < LOW_CONFIDENCE else []
    if start < today:
        flags.append(FLAG_MISSED)
    all_day = item["time"] is None  # a date with no time is all day, whatever the model said
    end, end_time = item["end_date"], None if all_day else item["end_time"]
    if end is None and end_time is not None:
        end = start  # an end time with no end date ends on the start day
    if end is not None and (end < start or (end == start and end_time is not None and not all_day
                                            and end_time < item["time"])):
        end, end_time = None, None  # an end before the start is no end
    explicit_end = end is not None
    if end is None and not all_day and (span := end_from_duration(start, item["time"], item.get("duration_minutes"))):
        end, end_time = date.fromisoformat(span[0]), span[1]  # rich mode: start plus the stated length
    duration = item.get("duration_minutes")
    if explicit_end:  # a stated end rules: the length on the wire is recomputed from it, so the two never disagree
        duration = span_minutes(start, item["time"], end, end_time) if "duration_minutes" in item else None
    if all_day:
        duration = None  # an all-day event has no length in minutes
    return EventCandidate(title=item["title"], start_date=start.isoformat(), start_time=item["time"],
                          all_day=all_day, end_date=end.isoformat() if end else None,
                          end_time=end_time, links=links, confidence=item["confidence"], flags=tuple(flags),
                          location=item.get("location"), notes=item.get("notes"),
                          duration_minutes=duration, attendees=item.get("attendees", ()))


def to_candidates(answer, today: date, resolve: Resolve, *, rich: bool = False,
                  kinds: tuple[str, ...] = DEFAULT_KINDS) -> tuple[tuple, int]:
    """``(candidates, dropped)`` for a model answer. One bad item never costs the others: an item that fails
    validation, has an empty title or a date beyond five years is dropped, and so is everything past
    ``MAX_ITEMS``; ``dropped`` counts them. ``rich`` also validates and maps the four rich fields (a missing one
    makes the item invalid); ``resolve`` is called as ``resolve(name, kind)`` with ``kind`` from ``kinds``. ``LlmInvalid`` only when the top-level shape is wrong or the answer
    had items and none survived (an empty list is a valid "nothing")."""
    if not isinstance(answer, dict) or not isinstance(answer.get("items"), list):
        raise _bad("bad answer shape")
    raws = answer["items"]
    out = []
    for raw in raws[:MAX_ITEMS]:
        try:
            item = _check_item(raw, today, kinds, rich)
        except (LlmInvalid, ArithmeticError, TypeError, ValueError):  # a hostile number costs only its item
            continue
        if item is None:
            continue
        links = tuple(LinkCandidate(text=t, kind=k, candidates=tuple(resolve(t, k))) for t, k in item["link_texts"])
        if item["kind"] == "event" and item["date"] is not None:
            out.append(_event(item, today, links))
        else:  # a task, or an event with no date, which becomes a task due today
            out.append(_task(item, today, links))
    if raws and not out:
        raise _bad("no usable item")
    return tuple(out), len(raws) - len(out)
