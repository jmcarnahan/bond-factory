"""Reminders: when one is due, scheduling the job, and firing it once.

``remind_minutes_before``: -2 none, -1 the morning of the due date (08:00 local), N >= 0 that many minutes before
the due time. A task with no due time counts as due at 08:00 local. The queue runs the job; the provider never does.
"""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import update

from bond_tasks_py.models import MORNING_OF, TaskStatus
from bond_tasks_py.protocols import Scheduler
from bond_tasks_py.timeutil import local_to_utc, parse_hhmm, to_naive_utc

JOB_TYPE = "task_reminder"
MORNING = time(8, 0)


def dedupe_key(task_id: str) -> str:
    return f"{JOB_TYPE}:{task_id}"


def compute_remind_at(due_date: date | None, due_time: str | None, remind_minutes_before: int, tz: str) -> datetime | None:
    """The reminder instant as naive UTC, or None (no date, or an encoding below -1: -2 none, -3 "use my default",
    which queues nothing here). ``tz`` is an IANA name."""
    if due_date is None or remind_minutes_before < MORNING_OF:
        return None
    if remind_minutes_before == MORNING_OF:
        return local_to_utc(due_date, MORNING, tz)
    clock = parse_hhmm(due_time) if due_time else MORNING
    return local_to_utc(due_date, clock, tz) - timedelta(minutes=remind_minutes_before)


def refresh_remind_at(task: Any, tz: str) -> None:
    """Recompute ``remind_at``; a changed instant clears ``reminded_at`` so the new time can fire."""
    new = compute_remind_at(task.due_date, task.due_time, task.remind_minutes_before, tz)
    if new != task.remind_at:
        task.reminded_at = None
    task.remind_at = new


def schedule_reminder(session: Any, task: Any, scheduler: Scheduler, *, tz: str) -> datetime | None:
    """Cancel any earlier job for the task, then enqueue one at ``remind_at``. Returns the instant, or None when
    nothing is scheduled (no reminder, not open, or already fired)."""
    refresh_remind_at(task, tz)
    key = dedupe_key(task.id)
    scheduler.cancel(session, dedupe_key=key)
    if task.remind_at is None or task.status != TaskStatus.OPEN.value or task.reminded_at is not None:
        return None
    scheduler.enqueue(session, job_type=JOB_TYPE, payload={"task_id": task.id}, run_at=task.remind_at, dedupe_key=key)
    return task.remind_at


def cancel_reminder(session: Any, task_id: str, scheduler: Scheduler) -> None:
    scheduler.cancel(session, dedupe_key=dedupe_key(task_id))


def fire_reminder(session: Any, task_model: Any, task_id: str, notify: Callable[[Any], None], *, now: datetime) -> bool:
    """Notify once, even when two workers run the job at the same time. False when there is nothing to do: the task is
    gone, not open, has no reminder, was already reminded, or its reminder moved later than ``now``. The claim is one
    conditional UPDATE on ``reminded_at IS NULL``: only the worker whose UPDATE changes a row notifies. A failing
    ``notify`` releases the claim and re-raises so the queue retries."""
    task = session.get(task_model, task_id)
    now = to_naive_utc(now)
    if task is None or task.status != TaskStatus.OPEN.value:
        return False
    if task.remind_at is None or task.remind_at > now:
        return False
    claim = (update(task_model).where(task_model.id == task_id, task_model.reminded_at.is_(None),
                                      task_model.status == TaskStatus.OPEN.value,
                                      task_model.remind_at == task.remind_at)
             .values(reminded_at=now).execution_options(synchronize_session=False))
    if session.execute(claim).rowcount != 1:
        session.expire(task)
        return False
    session.expire(task)
    try:
        notify(task)
    except Exception:
        release = (update(task_model).where(task_model.id == task_id, task_model.reminded_at == now)
                   .values(reminded_at=None).execution_options(synchronize_session=False))
        session.execute(release)
        session.expire(task)
        raise
    return True
