"""The due instant: zone arithmetic, the one overdue definition, and the computing and recomputing services.

Naive UTC in and out. Rules and reasons: docs/decisions/2026-11-11-due-instant.md. A local time that does not
exist (spring forward) moves forward and an ambiguous one (fall back) takes the first occurrence, as
``timeutil.local_to_utc`` already does.
"""

from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from bond_tasks_py.models import TaskStatus
from bond_tasks_py.protocols import Preferences, UserPrefs
from bond_tasks_py.timeutil import local_to_utc, to_naive_utc


def compute_due_at(due_date: date | None, due_time: str | None, *, writer_zone: str | None,
                   responsible_prefs: UserPrefs, app_tz: str, client_due_at: datetime | None = None
                   ) -> datetime | None:
    """The due instant of a task, or None when undated: a timed task uses the writer's zone, a date-only task the
    responsible user's end of day and zone. A client value is a hint for a timed task only.

    When ``due_at`` is recomputed: only when a write changes ``due_date``, ``due_time`` or ``assigned_user_id``
    to a value that DIFFERS from the stored one, so a form that resends unchanged values from another zone does
    not move a timed task's instant. Clearing ``due_date`` clears ``due_at``. A write that changes none of the
    three keeps ``due_at``."""
    raise NotImplementedError("due.compute_due_at is not implemented yet")


def end_of_day_due(day: date, eod: time, zone: str) -> datetime:
    """``day`` at ``eod`` in ``zone`` as naive UTC."""
    return local_to_utc(day, eod, zone)


def local_day_bounds(day: date, zone: str) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of a local calendar day as naive UTC; 23 to 25 hours on a daylight
    saving change day."""
    return local_to_utc(day, time(0, 0), zone), local_to_utc(day + timedelta(days=1), time(0, 0), zone)


def next_local_time(after_utc: datetime, clock: time, zone: str) -> datetime:
    """The first instant strictly after ``after_utc`` whose local wall clock is ``clock`` (one per local day)."""
    after = to_naive_utc(after_utc)
    day = after.replace(tzinfo=UTC).astimezone(ZoneInfo(zone)).date()
    candidate = local_to_utc(day, clock, zone)
    while candidate <= after:
        day += timedelta(days=1)
        candidate = local_to_utc(day, clock, zone)
    return candidate


def is_overdue(task: Any, now: datetime, *, viewer_today: date | None = None) -> bool:
    """The one definition: an open task is overdue when ``due_at < now``; a dated task whose ``due_at`` is not yet
    computed falls back to ``due_date < viewer_today`` (never overdue without ``viewer_today``)."""
    if task.status != TaskStatus.OPEN.value:
        return False
    due_at = getattr(task, "due_at", None)
    if due_at is not None:
        return to_naive_utc(due_at) < to_naive_utc(now)
    return bool(task.due_date is not None and viewer_today is not None and task.due_date < viewer_today)


def recompute_day_due(session: Any, *, task_model: Any, user_id: str, prefs: Preferences, tz: str,
                      now: datetime) -> int:
    """Recompute ``due_at`` of the user's open date-only tasks after their end of day or zone changed. Returns the
    number changed."""
    raise NotImplementedError("due.recompute_day_due is not implemented yet")


def backfill_due_at(session: Any, *, task_model: Any, prefs: Preferences, tz: str, now: datetime,
                    limit: int = 1000) -> int:
    """Fill ``due_at`` for dated tasks that have none (the sweep repairs them). Returns the number filled."""
    raise NotImplementedError("due.backfill_due_at is not implemented yet")


@cache
def _known_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def valid_zone(name: str) -> bool:
    """True when ``name`` is a known IANA zone name (checked against the zone list, so every platform agrees)."""
    return isinstance(name, str) and name in _known_zones()
