"""Ledger and outbox retention: what may be deleted without causing a re-send.

Deleting a ledger row lets its notice be claimed again if the stage is still current, so only rows that can never
be current again go: everything of a task closed for a while (or gone), close and due rows older than the longest
close window plus a day, and past rows except the newest sequence of each deadline."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import and_, delete, exists, select

from bond_tasks_py.models import TaskStatus
from bond_tasks_py.stages import deadline_token
from bond_tasks_py.sweep_claim import table_of
from bond_tasks_py.timeutil import to_naive_utc

CLOSE_DUE_DAYS = 8  # the close window is at most 7 days
PAST_DAYS = 2
READ_CHUNK = 1000  # ledger rows read at a time by the old-deadline rule


def prune_ledger(session: Any, *, task_model: Any, ledger_model: Any, outbox_model: Any, now: datetime,
                 closed_days: int = 30) -> int:
    """Delete the rows retention allows; returns the ledger rows deleted. Their outbox rows go with them.

    (a) every row of a task that is done or cancelled and was updated more than ``closed_days`` ago, and of a task
    that is gone; (b) for open tasks, close and due rows claimed more than 8 days ago; (c) for open tasks, past
    rows claimed more than 2 days ago except the newest sequence per (task, user, deadline token); (d) for open
    tasks, rows of an old deadline (their token differs from the task's current one) claimed more than 8 days
    ago. ``now`` may be aware."""
    now = to_naive_utc(now)
    tasks, led, out = table_of(task_model), table_of(ledger_model), table_of(outbox_model)
    is_open = exists().where(tasks.c.id == led.c.task_id, tasks.c.status == TaskStatus.OPEN.value)
    closed = exists().where(tasks.c.id == led.c.task_id, tasks.c.status != TaskStatus.OPEN.value,
                            tasks.c.updated_at < now - timedelta(days=closed_days))
    gone = ~exists().where(tasks.c.id == led.c.task_id)
    newer = led.alias("newer")
    superseded = exists().where(newer.c.task_id == led.c.task_id, newer.c.user_id == led.c.user_id,
                                newer.c.deadline_token == led.c.deadline_token, newer.c.stage == "past",
                                newer.c.seq > led.c.seq)
    rules = [
        closed | gone,
        and_(is_open, led.c.stage.in_(("close", "due")), led.c.claimed_at < now - timedelta(days=CLOSE_DUE_DAYS)),
        and_(is_open, led.c.stage == "past", led.c.claimed_at < now - timedelta(days=PAST_DAYS), superseded),
    ]
    total = 0
    for rule in rules:
        session.execute(delete(out).where(out.c.ledger_id.in_(select(led.c.id).where(rule))))
        total += session.execute(delete(led).where(rule)).rowcount
    total += _prune_old_deadlines(session, tasks, led, out, now)
    session.flush()
    return total


def _prune_old_deadlines(session: Any, tasks: Any, led: Any, out: Any, now: datetime) -> int:
    """Rule (d). The token is computed in Python (epoch minutes of the instant, or the ISO date), so the rows
    are read in chunks of 1,000 by id and the stale ids deleted chunk by chunk."""
    total, last_id = 0, ""
    while True:
        rows = session.execute(
            select(led.c.id, led.c.deadline_token, tasks.c.due_date, tasks.c.due_time, tasks.c.due_at)
            .join(tasks, tasks.c.id == led.c.task_id)
            .where(tasks.c.status == TaskStatus.OPEN.value, led.c.claimed_at < now - timedelta(days=CLOSE_DUE_DAYS),
                   led.c.id > last_id)
            .order_by(led.c.id).limit(READ_CHUNK)).all()
        if not rows:
            return total
        last_id = rows[-1].id
        stale = [r.id for r in rows if deadline_token(SimpleNamespace(
            due_date=r.due_date, due_time=r.due_time, due_at=r.due_at)) != r.deadline_token]
        for start in range(0, len(stale), 500):  # under SQLite's bind limit
            ids = stale[start:start + 500]
            session.execute(delete(out).where(out.c.ledger_id.in_(ids)))
            total += session.execute(delete(led).where(led.c.id.in_(ids))).rowcount
        if len(rows) < READ_CHUNK:
            return total
