"""What every tasks route file shares: one transaction, the clock, the viewer's zone, the wire item, the write hook.

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
from bond_tasks_py import TaskError
from fastapi import BackgroundTasks, Request
from sqlalchemy.orm import Session

from . import tasks_wiring, todo_wiring
from .db import session_scope
from .models.task_settings import TaskUserSettings
from .models.tasks import Task


@contextmanager
def unit(request: Request) -> Iterator[Session]:
    """One transaction: commit on success, roll back on any error. A coded error of the tasks, notify or push lib
    becomes the shared error body with its own status."""
    try:
        with session_scope(request.app.state.session_factory) as session:
            yield session
    except (TaskError, NoticeError, PushError) as exc:
        raise ApiError(exc.code, exc.message, status=exc.status) from None


async def check_body(request: Request) -> None:
    """A dependency for task writes: the two body errors the plan names get their own codes, not the generic
    `validation_error`. Priority is 1 to 3 (or null); `time_zone` is an IANA name (or null)."""
    try:
        body = await request.json()
    except ValueError:
        return  # not JSON: the normal body validation answers
    if not isinstance(body, dict):
        return
    priority = body.get("priority")
    if priority is not None and (isinstance(priority, bool) or priority not in (1, 2, 3)):
        raise ApiError("invalid_priority", "Priority is 1, 2 or 3.", status=422)
    zone = body.get("time_zone")
    if zone is not None and not (isinstance(zone, str) and tasks.valid_zone(zone)):
        raise ApiError("invalid_time_zone", "That is not a time zone name.", status=422)


def clock_now(request: Request) -> datetime:
    return request.app.state.clock.utcnow_naive()


def viewer_zone(request: Request, session: Session, user_id: str, asked: str | None = None) -> str:
    if asked:
        if not tasks.valid_zone(asked):
            raise ApiError("invalid_time_zone", "That is not a time zone name.", status=422)
        return asked
    return tasks.effective_zone(tasks.get_settings(session, TaskUserSettings, user_id), request.app.state.settings.tz)


def item(request: Request, session: Session, task: Task, zone: str) -> dict:
    now = clock_now(request)
    return tasks.task_item(task, today=tasks.viewer_today(now, zone), now=now,
                           names=tasks_wiring.user_names(session)(
                               [i for i in {task.owner_user_id, task.assigned_user_id} if i]))


def items(request: Request, session: Session, rows: list[Task], zone: str) -> list[dict]:
    now = clock_now(request)
    return tasks.task_items(rows, today=tasks.viewer_today(now, zone), now=now,
                            names=tasks_wiring.user_names(session))


def write_kwargs(request: Request, session: Session, user_id: str) -> dict:
    """The keyword arguments `create` and `update` take beyond the data: zone, preferences, link hook."""
    state = request.app.state
    stored = tasks.get_settings(session, TaskUserSettings, user_id).time_zone
    return {"now": clock_now(request), "tz": state.settings.tz, "user_exists": tasks_wiring.user_exists(session),
            "writer_zone": stored, "prefs": state.todo_prefs, "after_write": state.link_hook}


def after_write(request: Request, background: BackgroundTasks, session: Session, task: Task) -> None:
    """Inside the transaction: put away notices that no longer apply. Then queue the mirror pass for after the commit."""
    todo_wiring.after_task_write(session, task, clock_now(request))
    if task.mirror_status == "pending":
        background.add_task(tasks.sync_mirror, request.app.state.session_factory, Task, task.id,
                            request.app.state.mirror_providers, tz=request.app.state.settings.tz)
