"""The degraded fallback: model unavailable gives ONE task draft, never an event. Standard library only.

Cheap English and Spanish rules over the folded text (lower case, accents removed). A guess, flagged
``low_confidence``; the user reviews it before anything is saved.
"""

import re
import unicodedata
from datetime import date, timedelta

from bond_capture_py.candidates import FLAG_LOW_CONFIDENCE, TaskCandidate
from bond_capture_py.textclean import clean_text
from bond_capture_py.validate import HORIZON_DAYS

TITLE_CAP = 200
_DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
         "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
_DAY_RE = "(" + "|".join(_DAYS) + ")"
_MONTHS = {}
for _n, _names in enumerate((
        "january jan enero ene", "february feb febrero", "march mar marzo", "april apr abril abr",
        "may mayo", "june jun junio", "july jul julio", "august aug agosto ago",
        "september sept sep septiembre setiembre", "october oct octubre", "november nov noviembre",
        "december dec diciembre dic"), start=1):
    _MONTHS.update({name: _n for name in _names.split()})
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_MONTH_RE = f"({_MONTH_ALT})"
_HIGH = re.compile(r"\b(urgent|urgente|asap|important|importante|high priority|prioridad alta)\b")
_LOW = re.compile(r"\b(low priority|whenever|someday|cuando pueda|prioridad baja)\b")
_DAYPARTS = (("tonight", "19:00"), ("morning", "09:00"), ("afternoon", "14:00"), ("evening", "17:00"))
_NOT_A_TIME = r"(?![\d/])(?!\s*(?:days?|weeks?|dias?|semanas?|(?:of\s+|de\s+)?(?:" + _MONTH_ALT + r"))\b)"
_PREFIXED = re.compile(r"(?<![a-z])(?:at|by|@|before|until|around|a las|a la)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"
                       r"(?:\s*(?:de la|por la)\s*(manana|tarde|noche))?" + _NOT_A_TIME)
_MERIDIEM = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b")
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def fold(text: str) -> str:
    """Lower case with accents removed, so "mañana" and "manana" are the same word."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _hhmm(hour: int, minute: int, meridiem: str | None, daypart: str | None, morning: bool) -> str | None:
    """A bare hour (no am or pm, no daypart suffix) from 1 to 6 is the afternoon ("at 3" is 15:00, "at 6:30" is
    18:30) unless the phrase has a morning word, which keeps it as written. 7 to 12 and 13 to 23 are as written."""
    pm = meridiem == "pm" or daypart in ("tarde", "noche")
    am = meridiem == "am" or daypart == "manana"
    if pm and hour < 12:
        hour += 12
    elif am and hour == 12:
        hour = 0
    elif not (pm or am or morning) and 1 <= hour <= 6:
        hour += 12
    return f"{hour:02d}:{minute:02d}" if hour <= 23 and minute <= 59 else None


def _time(f: str, morning: bool) -> str | None:
    if re.search(r"\b(?:noon|mediodia)\b", f):
        return "12:00"
    for m in _PREFIXED.finditer(f):
        if found := _hhmm(int(m[1]), int(m[2] or 0), m[3], m[4], morning):
            return found
    for m in _MERIDIEM.finditer(f):
        if found := _hhmm(int(m[1]), int(m[2] or 0), m[3], None, morning):
            return found
    for m in _CLOCK.finditer(f):
        if found := _hhmm(int(m[1]), int(m[2]), None, None, morning):
            return found
    return None


def _daypart(f: str) -> str | None:
    return next((hhmm for word, hhmm in _DAYPARTS if re.search(rf"\b{word}\b", f)), None)


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_year_if_past(today: date, month: int, day: int) -> date | None:
    found = _safe(today.year, month, day)
    if found and found < today:
        found = _safe(today.year + 1, month, day)
    return found


def _day_of_month(today: date, day: int) -> date | None:
    found = _safe(today.year, today.month, day)
    if found and found >= today:
        return found
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return _safe(year, month, day)


def _end_of_month(today: date) -> date:
    first_next = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    return first_next - timedelta(days=1)


def _calendar_date(f: str, today: date) -> date | None:
    if m := re.search(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", f):  # an ISO date, anywhere in the phrase
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    if m := re.search(r"\b(?:by|on|before|due|para|el)\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])", f):
        first, second = int(m[1]), int(m[2])
        month, day = (first, second) if first <= 12 else (second, first)  # US order unless it cannot be one
        if m[3]:
            return _safe(int(m[3]) + (2000 if len(m[3]) == 2 else 0), month, day)
        return _next_year_if_past(today, month, day)
    tail = r"(?!\d|:\d|\s*[ap]m\b)"
    if m := re.search(rf"\b{_MONTH_RE}\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b{tail}", f):
        return _next_year_if_past(today, _MONTHS[m[1]], int(m[2]))
    if m := re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+|de\s+)?{_MONTH_RE}\b", f):
        return _next_year_if_past(today, _MONTHS[m[2]], int(m[1]))
    if m := re.search(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", f):
        return _day_of_month(today, int(m[1]))
    return None


def _date(f: str, today: date) -> date | None:
    """The date the note names, None when it names none. A bare weekday is its next occurrence after today."""
    if re.search(r"\b(?:day after tomorrow|pasado manana)\b", f):
        return today + timedelta(days=2)
    if re.search(r"\b(?:tomorrow|manana)\b", f):
        return today + timedelta(days=1)
    if re.search(r"\b(?:today|tonight|tonite|eod|end of day|hoy|esta noche)\b", f):
        return today
    if m := re.search(r"\b(?:in|en)\s+(\d{1,3})\s+(day|days|dia|dias|week|weeks|semana|semanas)\b", f):
        return today + timedelta(days=int(m[1]) * (7 if m[2].startswith(("w", "s")) else 1))
    if found := _calendar_date(f, today):
        return found
    if re.search(r"\b(?:end of (?:the )?month|fin de mes)\b", f):
        return _end_of_month(today)
    if re.search(r"\b(?:end of (?:the )?week|fin de (?:la )?semana)\b", f):
        return today + timedelta(days=(4 - today.weekday()) % 7 if today.weekday() <= 4 else 11 - today.weekday())
    next_monday = today + timedelta(days=7 - today.weekday())
    if m := re.search(rf"\b(?:next|proximo|proxima)\s+{_DAY_RE}\b|\b{_DAY_RE}\s+(?:que viene|proximo)\b", f):
        return next_monday + timedelta(days=_DAYS[m[1] or m[2]])
    if re.search(r"\b(?:next week|(?:la )?proxima semana|la semana que viene)\b", f):
        return next_monday
    if m := re.search(rf"\b{_DAY_RE}\b", f):
        return today + timedelta(days=(_DAYS[m[1]] - today.weekday()) % 7 or 7)
    return None


def degraded_draft(text: str, today: date) -> dict:
    """A ``TaskCandidate`` dict (``degraded`` true, ``confidence`` 0.2, flag ``low_confidence``) for the whole
    text: ONE task, never an event. The title is the text (200 characters); the date and time come from the
    word rules above; with no date found the due date is today and ``due_defaulted`` is true.

    Rules worth knowing: a bare weekday is its next occurrence after today; "next friday" is the Friday of
    NEXT WEEK (weeks start Monday), so on a Wednesday "Friday" is in two days and "next Friday" in nine. A bare
    numeric "M/D" counts only after by, on, before, due, para or el, and is US order unless the first number is
    above 12 ("31/12" is day/month). A bare hour from 1 to 6 (no am or pm) is the afternoon whether or not it
    has minutes ("at 3" is 15:00, "at 6:30" is 18:30) unless the phrase has a morning word, which keeps it as
    written ("tomorrow morning at 6:30" is 06:30); 7 to 12 are as written."""
    title = clean_text(text, TITLE_CAP)
    f = fold(text)
    morning = bool(re.search(r"\b(?:morning|(?:por|de|en) la manana)\b", f))
    time = _time(f, morning)
    # "por la manana" is a daypart, not the word for tomorrow
    f = re.sub(r"\b(?:por|de|en) la manana\b", " morning ", f)
    f = re.sub(r"\b(?:por|de) la tarde\b", " afternoon ", f)
    f = re.sub(r"\b(?:por|de) la noche\b", " evening ", f)
    f = f.replace("esta noche", "tonight")
    due = _date(f, today)
    time = time or _daypart(f)
    # The same clamps as the model path (validate.py): a date that has passed would make a task that is overdue
    # when saved, so it becomes today, defaulted, with its time cleared; a date beyond five years is ignored.
    if due is not None and due < today:
        due, time = None, None
    elif due is not None and due > today + timedelta(days=HORIZON_DAYS):
        due = None
    priority = 3 if _HIGH.search(f) else 1 if _LOW.search(f) else None
    draft = TaskCandidate(title=title, due_date=(due or today).isoformat(), due_time=time,
                          due_defaulted=due is None, priority=priority, confidence=0.2,
                          flags=(FLAG_LOW_CONFIDENCE,), degraded=True)
    return draft.to_dict()
