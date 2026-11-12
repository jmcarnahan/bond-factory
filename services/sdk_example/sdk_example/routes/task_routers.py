"""Mounts the lib routers: `make_tasks_router` at /tasks and `make_notices_router` at /notices.

What stays here is the app's part: the capability checks, the notices a task change puts away, the calendar mirror
after the commit, the link labels, the `prepare` rule and the work-day defaults. The routes themselves are the libs'.
The capture and link-search routes (`task_capture.py`) load before this file, like every `/tasks/<word>` path.
"""

from __future__ import annotations

from typing import Any

import bond_tasks_py as tasks
from bond_auth_py import has
from bond_notify_py import dismiss_stale
from bond_notify_py import routes as notice_routes
from bond_service_kit import ApiError
from bond_tasks_py import routes as task_routes
from fastapi import BackgroundTasks, FastAPI, Request

from .. import tasks_wiring, todo_wiring
from ..auth_dep import current_user, current_user_id, require_capability
from ..db import session_scope
from ..models.notices import Notice
from ..models.task_links import TaskLinkIndex
from ..models.task_settings import TaskUserSettings
from ..models.tasks import Task

READ_ALL = "tasks.read_all"


def require_read_all(request: Request) -> None:
    """Reading beyond your own tasks (scope=all, someone else's task) needs the `tasks.read_all` capability."""
    if not has(list(current_user(request).capabilities or []), READ_ALL):
        raise ApiError("forbidden", f"This needs the {READ_ALL} capability.", status=403)


def register(app: FastAPI) -> None:
    tasks_wiring.install(app)
    state = app.state

    def scope():
        return session_scope(state.session_factory)

    def now():
        return state.clock.utcnow_naive()  # read per call: a test or the fake clock may swap it

    def snapshot(session: Any, task_id: str) -> set[str]:
        return todo_wiring.recipients_of(session, task_id)

    def after_write(session: Any, task: Any, moment: Any, before: set[str] | None) -> None:
        todo_wiring.after_task_write(session, task, moment)
        if before is not None:
            todo_wiring.dismiss_for_those_who_left(session, task, before, moment)

    def queue_mirror(background: BackgroundTasks, task: Any) -> None:
        if task.mirror_status == "pending":
            background.add_task(tasks.sync_mirror, state.session_factory, Task, task.id, state.mirror_providers,
                                tz=state.settings.tz, draft_for=state.mirror_draft_for)

    def remove_mirror(background: BackgroundTasks, pointer: Any) -> None:
        background.add_task(tasks.remove_event, state.session_factory, state.mirror_providers, pointer)

    def moved(session: Any, task: Any, old_due_at: Any, moment: Any) -> None:
        """A date-only task's deadline moved with the work day or zone: its old notices go at once."""
        dismiss_stale(session, Notice, task.id, task.due_at, moment)

    def names(session: Any, ids: list[str]) -> dict[str, str]:
        return tasks_wiring.user_names(session)(ids)

    write = require_capability("tasks.write")
    app.include_router(task_routes.make_tasks_router(
        task_model=Task, settings_model=TaskUserSettings, link_index_model=TaskLinkIndex, session_scope=scope,
        user_dep=current_user_id, now=now, write_dep=write, read_all_dep=require_read_all, tz=state.settings.tz,
        defaults=state.default_prefs, prepare=todo_wiring.owner_edits_closed, link_hook=state.link_hook,
        labels=lambda session, links: state.contacts.labels(session, links), names=names,
        user_exists=lambda session, user_id: tasks_wiring.user_exists(session)(user_id),
        snapshot=snapshot, after_write=after_write, after_commit=queue_mirror,
        after_delete=lambda session, task_id, moment: todo_wiring.after_task_delete(session, task_id, moment),
        after_delete_commit=remove_mirror, on_recomputed=moved))

    def act_item(session: Any, task: Any, user_id: str) -> dict:
        zone = tasks.effective_zone(tasks.get_settings(session, TaskUserSettings, user_id, state.default_prefs),
                                    state.settings.tz)
        moment = now()
        return tasks.task_items([task], today=tasks.viewer_today(moment, zone), now=moment, names=names_of(session),
                                labels=lambda links: state.contacts.labels(session, links))[0]

    def names_of(session: Any):
        return tasks_wiring.user_names(session)

    def on_act(session: Any, notice: Any, action: str, user_id: str, moment: Any) -> dict:
        task = tasks.get(session, Task, notice.source_id or (notice.data or {}).get("task_id"))
        tasks.apply_notice_action(session, task=task, action=action, actor_user_id=user_id, now=moment)  # a TaskError is answered by the notices router
        if action != "snooze":  # done or cancel: every notice of the task goes
            todo_wiring.after_task_write(session, task, moment)
        return {"task": act_item(session, task, user_id)}

    def after_act(background: BackgroundTasks, notice: Any, result: Any) -> None:
        item = (result or {}).get("task") or {}  # on_act's answer: no state is kept between the two calls
        if item.get("mirror_status") == "pending":
            background.add_task(tasks.sync_mirror, state.session_factory, Task, item["id"], state.mirror_providers,
                                tz=state.settings.tz, draft_for=state.mirror_draft_for)

    app.include_router(notice_routes.make_notices_router(
        notice_model=Notice, session_scope=scope, user_dep=current_user_id, now=now, on_act=on_act,
        act_dep=write, after_act=after_act))
