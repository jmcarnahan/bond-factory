"""The TODO tables on the sync host: tasks, notices and push_devices (the libs ship the handlers).

    todo_routes(app)   {(table, action): route} for `routes/sync.py` to wrap as `Route(r.ops, r.handler, r.reads, r.optional)`;
                       task writes pass the same `prepare` rule as the REST routes (`todo_wiring.owner_edits_closed`)
    reject_for         a lib error (`TaskError`, `NoticeError`, `PushError`) becomes a sync verdict
    already_written    a replayed `put` of a row the user already owns is a success

A device writes only its own rows: `user_id` comes from the session in every handler, never from the op. A notice
accepts `read_at` and `dismissed_at` only (the server stamps its own clock); a push device its token and environment.
"""

from __future__ import annotations

from datetime import datetime

import bond_notify_py as inbox
import bond_push_py as push
import bond_tasks_py as tasks
from bond_notify_py import dismiss_stale
from bond_sync_py import rejected, written_by
from bond_tasks_py import TaskRoute, sync_routes
from fastapi import FastAPI

from . import tasks_wiring, todo_wiring
from .models.notices import Notice
from .models.push import PushDevice
from .models.sync import Note
from .models.task_links import TaskLinkIndex
from .models.task_settings import TaskUserSettings
from .models.tasks import Task

OWNER_COLUMN = {"tasks": (Task, "owner_user_id"), "notes": (Note, "owner_user_id"),
                "push_devices": (PushDevice, "user_id")}


def reject_for(session, user, op, exc):
    """Map a lib error to the sync vocabulary (forbidden, not_found, conflict, invalid)."""
    for verdict_for in (tasks.verdict_for, inbox.verdict_for, push.verdict_for):
        verdict = verdict_for(exc)
        if verdict:
            return rejected(op.seq, verdict[0], verdict[1])
    return None


def already_written(session, user, op) -> bool:
    model, column = OWNER_COLUMN.get(op.table, (Note, "owner_user_id"))
    return written_by(session, model, column, user, op.id)


def todo_routes(app: FastAPI) -> dict:
    tz = app.state.settings.tz
    state = app.state

    def _now() -> datetime:
        return state.clock.utcnow_naive()  # the app clock, so a pinned clock stamps REST and sync alike

    def zone_of(ctx, session, user_id: str) -> str | None:
        return tasks.get_settings(session, TaskUserSettings, user_id, state.default_prefs).time_zone

    def after_write(ctx, session, task) -> None:
        """Put away notices that no longer apply, then queue the calendar mirror for after the response (the ops have
        committed by then), as the REST routes do."""
        todo_wiring.after_task_write(session, task, _now())
        if task.mirror_status == "pending" and ctx.background is not None:
            ctx.background.add_task(tasks.sync_mirror, state.session_factory, Task, task.id, state.mirror_providers,
                                    tz=tz, draft_for=state.mirror_draft_for)

    def after_delete(ctx, session, pointer) -> None:
        if pointer is not None and ctx.background is not None:
            ctx.background.add_task(tasks.remove_event, state.session_factory, state.mirror_providers, pointer)

    def user_exists(user_id: str) -> bool:
        """The assignee must be an active user. A short read on its own session: the routes get no session to hand over."""
        with state.session_factory() as session:
            return tasks_wiring.user_exists(session)(user_id)

    def on_deleted(ctx, session, task_id: str, owner_user_id: str) -> None:
        todo_wiring.after_task_delete(session, task_id, _now())

    routes = sync_routes(Task, now=_now, tz=tz, user_exists=user_exists, after_write=after_write, after_delete=after_delete,
                         zone_of=zone_of, prefs=state.todo_prefs, link_hook=state.link_hook,
                         link_index_model=TaskLinkIndex, on_deleted=on_deleted,
                         prepare=todo_wiring.owner_edits_closed)
    base = routes[("tasks", None)]

    def handler(session, ctx, op, data) -> None:
        """A patch can reassign: whoever left owner and assignee keeps no live notice of the task."""
        before = todo_wiring.recipients_of(session, op.id) if op.op == "patch" else set()
        base.handler(session, ctx, op, data)
        task = session.get(Task, op.id) if before else None
        if task is not None:
            todo_wiring.dismiss_for_those_who_left(session, task, before, _now())

    routes[("tasks", None)] = TaskRoute(base.ops, handler, base.reads, base.optional)
    def moved(session, task, old_due_at, moment) -> None:
        dismiss_stale(session, Notice, task.id, task.due_at, moment)  # as the REST settings route does

    routes.update(tasks.settings_routes(TaskUserSettings, Task, now=_now, defaults=state.default_prefs, tz=tz,
                                        on_recomputed=moved))  # key ("task_user_settings", None): own row, id = user id
    routes.update(inbox.notice_routes(Notice, now=_now))
    routes.update(push.device_routes(PushDevice, now=_now))
    return routes
