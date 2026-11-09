"""Wires bond_tasks_py into the example: the job-queue scheduler, the reminder handler and the calendar mirror.

    AppScheduler    the lib's `Scheduler` over `bond_jobs.enqueue` (the dedupe key is the idempotency key)
    install(app)    registers the `task_reminder` handler; its `notify` appends to `app.state.notices` (a fake
                    notification channel that `GET /tasks/notices` reads back)
    MirrorProviders the lib's `MirrorProviders` over the user's live OAuth connection and `calendar_wiring`

Nothing here is Task-specific beyond the model class, so an app copies this file and swaps its own notifier.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any

import bond_calendar as cal
import bond_jobs
from bond_tasks_py import JOB_TYPE, fire_reminder
from bond_tasks_py.protocols import MirrorDraft
from fastapi import FastAPI
from sqlalchemy import delete

from . import calendar_wiring
from .db import session_scope
from .models.auth import User
from .models.connections import OAuthConnection
from .models.jobs import BackgroundJob
from .models.tasks import Task
from .oauth_wiring import FAKE_GOOGLE, FAKE_MICROSOFT
from .settings import Settings

#: registered OAuth provider name -> the label stored in tasks.external_provider
LABELS = {FAKE_GOOGLE: "google", FAKE_MICROSOFT: "microsoft", "google": "google", "microsoft": "microsoft"}
ORDER = {"fake": (FAKE_GOOGLE, FAKE_MICROSOFT), "real": ("google", "microsoft")}


class AppScheduler:
    """`Scheduler` over the example's job table. Cancel removes every job under the key that is not running, so a
    reminder that already ran can be scheduled again after its time moves."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def enqueue(self, session: Any, *, job_type: str, payload: dict, run_at: datetime, dedupe_key: str) -> None:
        bond_jobs.enqueue(session, BackgroundJob, job_type, payload, run_at=run_at, key=dedupe_key,
                          now=self.app.state.clock.now())

    def cancel(self, session: Any, *, dedupe_key: str) -> None:
        session.execute(delete(BackgroundJob).where(BackgroundJob.idempotency_key == dedupe_key,
                                                    BackgroundJob.status != "running"))


class _SessionMirror:
    """A `CalendarMirror` that opens its own session per call (the real providers borrow one for the token)."""

    def __init__(self, app: FastAPI, connection_id: str) -> None:
        self.app, self.connection_id = app, connection_id

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        with session_scope(self.app.state.session_factory) as session:
            row = session.get(OAuthConnection, self.connection_id)
            if row is None or row.revoked_at is not None:
                raise cal.ReconnectRequired("The calendar connection is gone.")
            provider = calendar_wiring.provider_for_connection(self.app, session, row)
            return getattr(provider, name)(*args, **kwargs)

    def create_event(self, draft: MirrorDraft) -> Any:
        return self._call("create_event", cal.CalendarEventDraft(
            subject=draft.subject, start=draft.start, end=draft.end, is_all_day=draft.is_all_day,
            location=draft.location, body=draft.body, body_type=draft.body_type,
            categories=list(draft.categories), reminder_minutes=draft.reminder_minutes))

    def update_event(self, event_id: str, patch: dict, *, etag: str | None = None) -> Any:
        patch = {**patch, "categories": list(patch.get("categories") or [])}
        return self._call("update_event", event_id, patch, etag=etag)

    def delete_event(self, event_id: str) -> None:
        self._call("delete_event", event_id)

    def get_event(self, event_id: str) -> Any:
        return self._call("get_event", event_id)


class MirrorProviders:
    """`for_user`: the person's live connection (Google first, then Microsoft), or None."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def for_user(self, session: Any, user_id: str) -> tuple[str, _SessionMirror] | None:
        settings: Settings = self.app.state.settings
        for name in ORDER["fake" if settings.mode == "fake" else "real"]:
            connection = calendar_wiring.live_connection(session, user_id, name)
            if connection is not None:
                return LABELS[name], _SessionMirror(self.app, connection.id)
        return None


NOTICE_LIMIT = 500


def notices(app: FastAPI) -> deque[dict]:
    """The fake notification channel: the newest 500 notices, in memory."""
    if getattr(app.state, "notices", None) is None:
        app.state.notices = deque(maxlen=NOTICE_LIMIT)
    return app.state.notices


def install(app: FastAPI) -> None:
    """Idempotent. Builds the scheduler and providers and registers the reminder job handler."""
    if getattr(app.state, "tasks_scheduler", None) is not None:
        return
    app.state.tasks_scheduler = AppScheduler(app)
    app.state.mirror_providers = MirrorProviders(app)
    notices(app)

    @app.state.job_registry.handler(JOB_TYPE)
    def task_reminder(session: Any, payload: dict, now: datetime) -> dict:
        def notify(task: Task) -> None:
            who = task.assigned_user_id or task.owner_user_id
            remind_at = task.remind_at.strftime("%Y-%m-%dT%H:%M:%SZ") if task.remind_at else None
            if any(n["task_id"] == task.id and n["remind_at"] == remind_at for n in notices(app)):
                return  # the job ran before and its transaction rolled back after notifying: not a second notice
            notices(app).append({
                "task_id": task.id, "title": task.title, "user_id": who, "owner_user_id": task.owner_user_id,
                "assigned_user_id": task.assigned_user_id,
                "remind_at": remind_at,
                "fired_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "message": f"Reminder: {task.title}",
            })

        fired = fire_reminder(session, Task, payload["task_id"], notify, now=now)
        return {"summary": "reminded" if fired else "nothing to remind", "skipped": not fired,
                "reason": None if fired else "not_due_or_done"}


def user_names(session: Any):
    """A `names` callable for the lib's serializer: user id to display name."""

    def names(ids: list[str]) -> dict[str, str]:
        rows = session.query(User).filter(User.id.in_(ids)).all()
        return {u.id: u.name or u.email for u in rows}

    return names


def user_exists(session: Any):
    def exists(user_id: str) -> bool:
        user = session.get(User, user_id)
        return user is not None and bool(user.is_active)

    return exists
