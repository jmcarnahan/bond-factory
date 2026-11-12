"""The due instant: zone arithmetic, the one overdue definition, and the computing and recomputing services.

Naive UTC in and out. Rules and reasons: docs/decisions/2026-11-11-due-instant.md. A local time that does not
exist (spring forward) moves forward and an ambiguous one (fall back) takes the first occurrence, as
``timeutil.local_to_utc`` already does.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy import and_, or_, select

from bond_tasks_py.models import TaskStatus
from bond_tasks_py.protocols import Preferences, UserPrefs
from bond_tasks_py.timeutil import local_to_utc, parse_hhmm, to_naive_utc


def compute_due_at(due_date: date | None, due_time: str | None, *, writer_zone: str | None,
                   responsible_prefs: UserPrefs, app_tz: str, client_due_at: datetime | None = None,
                   sent_zone: str | None = None) -> datetime | None:
    """The due instant of a task, or None when undated: a timed task uses the writer's zone, a date-only task the
    responsible user's end of day and zone. A client value is a hint for a timed task only. ``writer_zone`` is the
    zone to compute with when no hint is accepted (the zone sent, else the stored one); a hint is checked only
    against ``sent_zone``, the zone name that came with the same write, and otherwise accepted when plausible.

    When ``due_at`` is recomputed: only when a write changes ``due_date``, ``due_time`` or ``assigned_user_id``
    to a value that DIFFERS from the stored one, so a form that resends unchanged values from another zone does
    not move a timed task's instant. Clearing ``due_date`` clears ``due_at``. A write that changes none of the
    three keeps ``due_at``."""
    if due_date is None:
        return None
    if due_time:
        wall = datetime.combine(due_date, parse_hhmm(due_time))
        zone = writer_zone if writer_zone and valid_zone(writer_zone) else app_tz
        computed = local_to_utc(due_date, parse_hhmm(due_time), zone).replace(second=0, microsecond=0)
        if client_due_at is not None and _hint_ok(wall, to_naive_utc(client_due_at), sent_zone):
            return to_naive_utc(client_due_at).replace(second=0, microsecond=0)
        return computed
    zone = next((z for z in (responsible_prefs.time_zone, writer_zone) if z and valid_zone(z)), app_tz)
    return local_to_utc(due_date, responsible_prefs.end_of_day, zone).replace(second=0, microsecond=0)


def _hint_ok(wall: datetime, client: datetime, sent_zone: str | None) -> bool:
    """A device's ``due_at`` for a timed task: a plausible whole-quarter-hour offset from the wall clock, and equal to
    the zone's own result when a valid zone name came with it. Anything else is ignored, never an error."""
    offset = wall - client
    if offset % timedelta(minutes=15) != timedelta(0) or not timedelta(hours=-12) <= offset <= timedelta(hours=14):
        return False
    if sent_zone and valid_zone(sent_zone):
        return local_to_utc(wall.date(), wall.time(), sent_zone) == client
    return True


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
                      now: datetime, on_recomputed: Callable[[Any, datetime | None], None] | None = None) -> int:
    """Recompute ``due_at`` of the user's open date-only tasks after their end of day or zone changed. Returns the
    number changed. ``on_recomputed(task, old_due_at)`` is called once per task whose ``due_at`` really changed,
    after the flush (``task.due_at`` is the new value)."""
    prefs_of = prefs.for_user(session, user_id)
    tasks = session.execute(select(task_model).where(
        task_model.status == TaskStatus.OPEN.value, task_model.due_date.is_not(None), task_model.due_time.is_(None),
        or_(task_model.assigned_user_id == user_id,
            and_(task_model.assigned_user_id.is_(None), task_model.owner_user_id == user_id)))).scalars().all()
    moved: list[tuple[Any, datetime | None]] = []
    for task in tasks:
        new = compute_due_at(task.due_date, None, writer_zone=None, responsible_prefs=prefs_of, app_tz=tz)
        if new != task.due_at:
            moved.append((task, task.due_at))
            task.due_at = new
    if moved:
        session.flush()
        if on_recomputed is not None:
            for task, old in moved:
                on_recomputed(task, old)
    return len(moved)


def backfill_due_at(session: Any, *, task_model: Any, prefs: Preferences, tz: str, now: datetime,
                    limit: int = 1000) -> int:
    """Fill ``due_at`` for dated tasks that have none (the sweep repairs them). Returns the number filled."""
    memo: dict[str, UserPrefs] = {}

    def prefs_of(user_id: str) -> UserPrefs:
        if user_id not in memo:
            memo[user_id] = prefs.for_user(session, user_id)
        return memo[user_id]

    tasks = session.execute(select(task_model).where(task_model.due_date.is_not(None), task_model.due_at.is_(None))
                            .order_by(task_model.created_at, task_model.id).limit(limit)).scalars().all()
    for task in tasks:
        responsible = prefs_of(task.assigned_user_id or task.owner_user_id)
        writer = prefs_of(task.created_by).time_zone if task.due_time else None
        task.due_at = compute_due_at(task.due_date, task.due_time, writer_zone=writer, responsible_prefs=responsible,
                                     app_tz=tz)
    if tasks:
        session.flush()
    return len(tasks)


@cache
def _known_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def valid_zone(name: str) -> bool:
    """True when ``name`` is a known IANA zone name (checked against the zone list, so every platform agrees)."""
    return isinstance(name, str) and name in _known_zones()
