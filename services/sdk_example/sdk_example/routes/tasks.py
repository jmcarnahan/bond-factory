"""Tasks: the reference wiring of bond_tasks_py (CRUD and the status changes; the rest are in `task_*.py`).

    GET    /tasks                          list (scope, status, date window, owner/assignee, link filters)
    GET    /tasks/summary                  {open, overdue, due_today, no_date} for the caller
    GET    /tasks/{id}                     one task
    POST   /tasks                          create (201); a client-chosen id replayed by its owner returns the row
    PUT    /tasks/{id}                     edit (omitted = unchanged, null clears)
    POST   /tasks/{id}/complete | /reopen | /cancel   (cancel is owner-only, and so is undoing a cancel)
    DELETE /tasks/{id}                     hard delete (204), owner only
    PUT    /tasks/{id}/checklist/{item_id} {"done": bool}

Every read takes `time_zone` (an IANA name; else the person's stored zone, else the service default) and measures
`overdue` against the clock: open and `due_at < now`. Writes need the `tasks.write` capability. A write and the
notices it makes stale commit together; the calendar mirror runs as a background task after the commit and never fails
the request.

Static paths (`/tasks/today`, `/tasks/settings`, `/tasks/parse`, `/tasks/links/search`) live in `task_*.py`, which load
BEFORE this file (modules register in name order), so `/tasks/{task_id}` never swallows them.
"""

from __future__ import annotations

from datetime import date

import bond_tasks_py as tasks
from bond_auth_py import has
from bond_service_kit import ApiError
from bond_tasks_py import TaskCreate, TaskFilters, TaskUpdate
from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from .. import tasks_wiring, todo_wiring
from ..auth_dep import current_user, current_user_id, require_capability
from ..models.task_links import TaskLinkIndex
from ..models.tasks import Task
from ..task_support import after_write, check_body, clock_now, item, items, unit, viewer_zone, write_kwargs

write = require_capability("tasks.write")
READ_ALL = "tasks.read_all"


class ChecklistTick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool


def require_read_all(request: Request) -> None:
    """Reading beyond your own tasks (scope=all, someone else's task) needs the `tasks.read_all` capability."""
    if not has(list(current_user(request).capabilities or []), READ_ALL):
        raise ApiError("forbidden", f"This needs the {READ_ALL} capability.", status=403)


def register(app: FastAPI) -> None:
    tasks_wiring.install(app)

    @app.get("/tasks")
    def list_tasks(
        request: Request, user_id: str = Depends(current_user_id), scope: str = Query("mine", pattern="^(mine|all)$"),
        status: str = Query("open", pattern="^(open|done|all)$"), time_zone: str | None = None,
        on_or_before: date | None = None, due_from: date | None = None, due_to: date | None = None,
        include_undated: bool = False, no_date: bool = False, owner_user_id: str | None = None,
        assigned_user_id: str | None = None, assigned_to_me: bool = False, link_kind: str | None = None,
        link_id: str | None = None, limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
    ) -> dict:
        filters = TaskFilters(scope=scope, status=status, on_or_before=on_or_before, due_from=due_from,
                              due_to=due_to, include_undated=include_undated, no_date=no_date,
                              owner_user_id=owner_user_id, assigned_user_id=assigned_user_id,
                              assigned_to_me=assigned_to_me, link_kind=link_kind, link_id=link_id)
        if scope == "all":
            require_read_all(request)
        with unit(request) as session:
            zone = viewer_zone(request, session, user_id, time_zone)
            rows, total = tasks.list_tasks(session, task_model=Task, user_id=user_id, filters=filters, limit=limit,
                                           offset=offset, link_index_model=TaskLinkIndex, viewer_zone=zone,
                                           now=clock_now(request))
            out = items(request, session, rows, zone)
        return {"items": out, "total": total, "limit": limit, "offset": offset}

    @app.get("/tasks/summary")
    def summary(request: Request, time_zone: str | None = None, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            zone = viewer_zone(request, session, user_id, time_zone)
            now = clock_now(request)
            return tasks.summary(session, task_model=Task, user_id=user_id, now=now, viewer_zone=zone)

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str, request: Request, time_zone: str | None = None,
                 user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            task = tasks.get(session, Task, task_id)
            if not tasks.service.is_editor(task, user_id):
                require_read_all(request)
            return item(request, session, task, viewer_zone(request, session, user_id, time_zone))

    @app.post("/tasks", status_code=201, dependencies=[Depends(check_body)])
    def create_task(body: TaskCreate, request: Request, background: BackgroundTasks, time_zone: str | None = None,
                    user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.create(session, task_model=Task, owner_user_id=user_id, actor_user_id=user_id, data=body,
                                **write_kwargs(request, session, user_id))
            after_write(request, background, session, task)
            return item(request, session, task, viewer_zone(request, session, user_id, time_zone))

    @app.put("/tasks/{task_id}", dependencies=[Depends(check_body)])
    def update_task(task_id: str, body: TaskUpdate, request: Request, background: BackgroundTasks,
                    time_zone: str | None = None, user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            before = todo_wiring.recipients_of(session, task_id)
            task = tasks.update(session, task=tasks.get(session, Task, task_id), actor_user_id=user_id, data=body,
                                **write_kwargs(request, session, user_id))
            after_write(request, background, session, task)
            todo_wiring.dismiss_for_those_who_left(session, task, before, clock_now(request))
            return item(request, session, task, viewer_zone(request, session, user_id, time_zone))

    def lifecycle(change, name: str):
        """One handler per status change: apply it, put away stale notices, answer the item."""

        @app.post(f"/tasks/{{task_id}}/{name}", name=f"{name}_task")
        def handler(task_id: str, request: Request, background: BackgroundTasks, time_zone: str | None = None,
                    user_id: str = Depends(write)) -> dict:
            with unit(request) as session:
                task = change(session, tasks.get(session, Task, task_id), user_id, clock_now(request))
                after_write(request, background, session, task)
                return item(request, session, task, viewer_zone(request, session, user_id, time_zone))

        return handler

    lifecycle(tasks.complete, "complete")
    lifecycle(tasks.reopen, "reopen")
    lifecycle(tasks.cancel, "cancel")

    @app.delete("/tasks/{task_id}", status_code=204)
    def delete_task(task_id: str, request: Request, background: BackgroundTasks,
                    user_id: str = Depends(write)) -> Response:
        with unit(request) as session:
            pointer = tasks.delete(session, tasks.get(session, Task, task_id), user_id, link_index_model=TaskLinkIndex)
            todo_wiring.after_task_delete(session, task_id, clock_now(request))
        if pointer is not None:
            background.add_task(tasks.remove_event, request.app.state.session_factory,
                                request.app.state.mirror_providers, pointer)
        return Response(status_code=204)

    @app.put("/tasks/{task_id}/checklist/{item_id}")
    def tick_item(task_id: str, item_id: str, body: ChecklistTick, request: Request, time_zone: str | None = None,
                  user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.get(session, Task, task_id)
            tasks.set_checklist_item(task, item_id, body.done, clock_now(request), actor_user_id=user_id)
            return item(request, session, task, viewer_zone(request, session, user_id, time_zone))
