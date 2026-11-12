"""The notice sweep wired two ways. Both call `run_sweep`.

    POST /jobs/tick (fake mode)     routes/jobs.py runs `sweep_app` at the pinned time, then the due jobs
    worker loop                     `before_hook(app)` as `bond_jobs.tick(..., before=..., before_every=BEFORE_EVERY)`
    scripts/sweep_interval.py       a loop that needs no jobs table: `run_sweep` plus `run_prune` every N seconds

`run_sweep` is two steps in two transactions: claim (`sweep_due` writes the ledger, the outbox rows and the inbox
notices together, then commits) and deliver (`deliver_pending` leases, sends and stamps, committing per row). The push
channel exists only when a sender is given; without one the sweep still fills the inbox.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Any

from bond_notify_py import InboxNotifier, prune_notices
from bond_push_py import PushNotifier
from bond_tasks_py import deliver_pending, prune_ledger, sweep_due
from fastapi import FastAPI

from .models.notices import Notice
from .models.push import PushDevice
from .models.task_ledger import TaskNoticeLedger, TaskNoticeOutbox
from .models.tasks import Task

CHANNEL = "push"
BEFORE_EVERY = 30.0  # seconds: the real loop's hook runs at most this often


def run_sweep(factory: Callable[[], Any], *, prefs: Any, tz: str, sender: Any, now: datetime) -> dict:
    """Claim what is due as of `now` (naive UTC), then deliver the queued pushes. `factory` opens sessions on an engine
    prepared with `sqlite_savepoint_setup` when it is SQLite. Returns both result records as dicts."""
    with factory() as session:
        claimed = sweep_due(
            session, task_model=Task, ledger_model=TaskNoticeLedger, outbox_model=TaskNoticeOutbox, now=now,
            prefs=prefs, tz=tz, transactional=[InboxNotifier(Notice)], channels=[CHANNEL] if sender else [])
        session.commit()
    delivered: dict = {}
    if sender is not None:
        with factory() as session:
            delivered = asdict(deliver_pending(
                session, ledger_model=TaskNoticeLedger, outbox_model=TaskNoticeOutbox, now=now,
                notifiers={CHANNEL: PushNotifier(PushDevice, sender)}, commit=session.commit, task_model=Task))
    return {"sweep": asdict(claimed), "deliver": delivered}


def run_prune(factory: Callable[[], Any], *, now: datetime) -> dict:
    """Retention for the ledger, the outbox and the inbox."""
    with factory() as session:
        ledger = prune_ledger(session, task_model=Task, ledger_model=TaskNoticeLedger,
                              outbox_model=TaskNoticeOutbox, now=now)
        notices = prune_notices(session, Notice, now)
        session.commit()
    return {"ledger": ledger, "notices": notices}


def sweep_app(app: FastAPI, now: datetime) -> dict:
    state = app.state
    return run_sweep(state.session_factory, prefs=state.todo_prefs, tz=state.settings.tz, sender=state.push_sender,
                     now=now)


def before_hook(app: FastAPI, then: Callable[[Any, datetime], None] | None = None) -> Callable[[Any, datetime], None]:
    """The `before` hook for `bond_jobs.tick` (pass `before_every=BEFORE_EVERY` with it). The tick hands over its own
    session for the app's scheduling work (`then`, for example the daily prune job); the sweep opens its own
    sessions because `deliver_pending` commits row by row."""

    def hook(session: Any, now: datetime) -> None:
        if then is not None:
            then(session, now)
        session.commit()
        sweep_app(app, now)

    return hook
