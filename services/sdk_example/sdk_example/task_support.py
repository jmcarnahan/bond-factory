"""What the capture and push routes share: one transaction, the clock, the viewer's zone.

The viewer's zone is, in order: the `time_zone` query value, the person's stored setting, the service default
(`SDK_EXAMPLE_TZ`). Every task read passes `now` with it, so `overdue` is one rule everywhere: open and `due_at < now`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import bond_tasks_py as tasks
from bond_notify_py import NoticeError
from bond_push_py import PushError
from bond_service_kit import ApiError
from bond_tasks_py import TaskError, UserPrefs
from fastapi import Request
from sqlalchemy.orm import Session

from .db import session_scope
from .models.task_settings import TaskUserSettings


@contextmanager
def unit(request: Request) -> Iterator[Session]:
    """One transaction: commit on success, roll back on any error. A coded error of the tasks, notify or push lib
    becomes the shared error body with its own status."""
    try:
        with session_scope(request.app.state.session_factory) as session:
            yield session
    except (TaskError, NoticeError, PushError) as exc:
        raise ApiError(exc.code, exc.message, status=exc.status) from None


def clock_now(request: Request) -> datetime:
    return request.app.state.clock.utcnow_naive()


def prefs_of(request: Request, session: Session, user_id: str) -> UserPrefs:
    """The person's effective preferences: what they stored over the app's default work day."""
    return tasks.get_settings(session, TaskUserSettings, user_id, request.app.state.default_prefs)


def viewer_zone(request: Request, session: Session, user_id: str, asked: str | None = None) -> str:
    if asked:
        if not tasks.valid_zone(asked):
            raise ApiError("invalid_time_zone", "That is not a time zone name.", status=422)
        return asked
    return tasks.effective_zone(prefs_of(request, session, user_id), request.app.state.settings.tz)
