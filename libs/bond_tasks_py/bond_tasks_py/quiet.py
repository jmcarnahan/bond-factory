"""Quiet hours are derived: after ``end_of_day`` until ``start_of_day`` (neither instant is quiet)."""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from bond_tasks_py.due import next_local_time
from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.timeutil import to_naive_utc


def in_quiet_hours(prefs: UserPrefs, zone: str, now: datetime) -> bool:
    """True when ``now`` (naive UTC, truncated to the minute: stages are minute-aligned) is quiet for the user in ``zone``: strictly after ``end_of_day`` and strictly
    before ``start_of_day``. A work day that spans midnight (start later than end) is quiet between the two; equal
    times mean there are no quiet hours."""
    clock = to_naive_utc(now).replace(second=0, microsecond=0, tzinfo=UTC).astimezone(ZoneInfo(zone)).time()
    start, end = prefs.start_of_day, prefs.end_of_day
    if start == end:
        return False
    if start < end:
        return clock > end or clock < start
    return end < clock < start


def next_work_start(prefs: UserPrefs, zone: str, now: datetime) -> datetime:
    """The next ``start_of_day`` instant after ``now`` as naive UTC."""
    return next_local_time(now, prefs.start_of_day, zone)


def sendable(task: Any, stage: str, prefs: UserPrefs, zone: str, now: datetime) -> bool:
    """May a notice of ``stage`` go out at ``now``? The due stage always may (it lasts 15 minutes). The close
    stage of a task with an explicit time may too: the user chose that time. Everything else (the close stage of
    a date-only task, every past stage) waits for the work day."""
    if stage == "due":
        return True
    if stage == "close" and getattr(task, "due_time", None):
        return True
    return not in_quiet_hours(prefs, zone, now)
