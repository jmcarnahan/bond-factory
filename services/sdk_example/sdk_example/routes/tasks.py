"""Tasks: the reference wiring of bond_tasks_py.

    GET    /tasks                          list (scope, status, date window, owner/assignee, link filters);
                                           scope=all needs `tasks.read_all`, as does reading another person's task
    GET    /tasks/summary                  {open, overdue, due_today, no_date} for the caller
    GET    /tasks/notices                  fake mode only: the reminders the job queue has fired for the caller
    GET    /tasks/{id}                     one task
    POST   /tasks                          create (201); a client-chosen id replayed by its owner returns the row
    PUT    /tasks/{id}                     edit (omitted = unchanged, null clears)
    POST   /tasks/{id}/complete | /reopen | /cancel   (cancel is owner-only, and so is undoing a cancel)
    DELETE /tasks/{id}                     hard delete (204), owner only
    PUT    /tasks/{id}/checklist/{item_id} {"done": bool}

Writes need the `tasks.write` capability. A write, its reminder job and its pending mirror state commit together; the
calendar mirror then runs as a background task after the commit and never fails the request.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import bond_tasks_py as tasks
from bond_auth_py import has
from bond_service_kit import ApiError
from bond_tasks_py import TaskCreate, TaskError, TaskFilters, TaskUpdate
from fastapi import BackgroundTasks, Depends, FastAPI, Query, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from .. import tasks_wiring
from ..auth_dep import current_user, current_user_id, require_capability
from ..db import session_scope
from ..models.tasks import Task

write = require_capability("tasks.write")
READ_ALL = "tasks.read_all"


class ChecklistTick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool


@contextmanager
def unit(request: Request) -> Iterator[Session]:
    """One transaction: commit on success, roll back on any error. A `TaskError` becomes the shared error body."""
    try:
        with session_scope(request.app.state.session_factory) as session:
            yield session
    except TaskError as exc:
        raise ApiError(exc.code, exc.message, status=exc.status) from None


def require_read_all(request: Request) -> None:
    """Reading beyond your own tasks (scope=all, someone else's task) needs the `tasks.read_all` capability."""
    if not has(list(current_user(request).capabilities or []), READ_ALL):
        raise ApiError("forbidden", f"This needs the {READ_ALL} capability.", status=403)


def clock_now(request: Request):
    return request.app.state.clock.utcnow_naive()


def client_today(request: Request, today: date | None) -> date:
    return today or request.app.state.clock.today(request.app.state.settings.tz)


def after_write(request: Request, background: BackgroundTasks, session: Session, task: Task) -> None:
    """Inside the transaction: keep the reminder job in step. Then queue the mirror pass for after the commit."""
    app, tz = request.app, request.app.state.settings.tz
    tasks.schedule_reminder(session, task, app.state.tasks_scheduler, tz=tz)
    if task.mirror_status == "pending":
        background.add_task(tasks.sync_mirror, app.state.session_factory, Task, task.id, app.state.mirror_providers,
                            tz=tz)


def item(session: Session, task: Task, today: date) -> dict:
    return tasks.task_item(task, today=today, names=tasks_wiring.user_names(session)(
        [i for i in {task.owner_user_id, task.assigned_user_id} if i]))


def register(app: FastAPI) -> None:
    tasks_wiring.install(app)

    @app.get("/tasks")
    def list_tasks(
        request: Request, user_id: str = Depends(current_user_id), scope: str = Query("mine", pattern="^(mine|all)$"),
        status: str = Query("open", pattern="^(open|done|all)$"), today: date | None = None,
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
            rows, total = tasks.list_tasks(session, task_model=Task, user_id=user_id, filters=filters, limit=limit,
                                           offset=offset)
            items = tasks.task_items(rows, today=client_today(request, today), names=tasks_wiring.user_names(session))
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/tasks/summary")
    def summary(request: Request, today: date | None = None, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            return tasks.summary(session, task_model=Task, user_id=user_id, today=client_today(request, today))

    @app.get("/tasks/notices")
    def notices(request: Request, user_id: str = Depends(current_user_id)) -> dict:
        """Fake mode only: what the reminder job has 'sent' to this person (the example's stand-in for a push)."""
        if request.app.state.settings.mode != "fake":
            raise ApiError("not_found", "Not found.", status=404)
        mine = [n for n in tasks_wiring.notices(request.app) if user_id in (n["owner_user_id"], n["assigned_user_id"])]
        return {"items": mine}

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str, request: Request, today: date | None = None,
                 user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            task = tasks.get(session, Task, task_id)
            if not tasks.service.is_editor(task, user_id):
                require_read_all(request)
            return item(session, task, client_today(request, today))

    @app.post("/tasks", status_code=201)
    def create_task(body: TaskCreate, request: Request, background: BackgroundTasks, today: date | None = None,
                    user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.create(session, task_model=Task, owner_user_id=user_id, actor_user_id=user_id, data=body,
                                now=clock_now(request), tz=request.app.state.settings.tz,
                                user_exists=tasks_wiring.user_exists(session))
            after_write(request, background, session, task)
            return item(session, task, client_today(request, today))

    @app.put("/tasks/{task_id}")
    def update_task(task_id: str, body: TaskUpdate, request: Request, background: BackgroundTasks,
                    today: date | None = None, user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.update(session, task=tasks.get(session, Task, task_id), actor_user_id=user_id, data=body,
                                now=clock_now(request), tz=request.app.state.settings.tz,
                                user_exists=tasks_wiring.user_exists(session))
            after_write(request, background, session, task)
            return item(session, task, client_today(request, today))

    @app.post("/tasks/{task_id}/complete")
    def complete_task(task_id: str, request: Request, background: BackgroundTasks, today: date | None = None,
                      user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.complete(session, tasks.get(session, Task, task_id), user_id, clock_now(request))
            after_write(request, background, session, task)
            return item(session, task, client_today(request, today))

    @app.post("/tasks/{task_id}/reopen")
    def reopen_task(task_id: str, request: Request, background: BackgroundTasks, today: date | None = None,
                    user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.reopen(session, tasks.get(session, Task, task_id), user_id, clock_now(request))
            after_write(request, background, session, task)
            return item(session, task, client_today(request, today))

    @app.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str, request: Request, background: BackgroundTasks, today: date | None = None,
                    user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.cancel(session, tasks.get(session, Task, task_id), user_id, clock_now(request))
            after_write(request, background, session, task)
            return item(session, task, client_today(request, today))

    @app.delete("/tasks/{task_id}", status_code=204)
    def delete_task(task_id: str, request: Request, background: BackgroundTasks,
                    user_id: str = Depends(write)) -> Response:
        with unit(request) as session:
            pointer = tasks.delete(session, tasks.get(session, Task, task_id), user_id)
            tasks.cancel_reminder(session, task_id, request.app.state.tasks_scheduler)
        if pointer is not None:
            background.add_task(tasks.remove_event, request.app.state.session_factory,
                                request.app.state.mirror_providers, pointer)
        return Response(status_code=204)

    @app.put("/tasks/{task_id}/checklist/{item_id}")
    def tick_item(task_id: str, item_id: str, body: ChecklistTick, request: Request, today: date | None = None,
                  user_id: str = Depends(write)) -> dict:
        with unit(request) as session:
            task = tasks.get(session, Task, task_id)
            tasks.set_checklist_item(task, item_id, body.done, clock_now(request), actor_user_id=user_id)
            return item(session, task, client_today(request, today))
