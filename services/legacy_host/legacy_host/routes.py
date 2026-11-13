"""The host's OWN task routes over `bond_tasks_py.service` (not `make_tasks_router`).

    POST /tasks   GET /tasks   GET /tasks/{id}   PUT /tasks/{id}   POST /tasks/{id}/complete|reopen
    DELETE /tasks/{id}

Bodies take both vocabularies (see `bodies.split`); answers are `wire.legacy_item`. A `TaskError` anywhere is
turned into the legacy error body by the handler in `app.py`.
"""

from __future__ import annotations

from typing import Any

import bond_tasks_py as tasks
from bond_tasks_py import StoredPreferences, TaskCreate, TaskFilters, TaskUpdate
from bond_tasks_py import UserPrefs as WorkDay
from fastapi import APIRouter, Depends, Query, Request, Response

from .bodies import split
from .db import session_scope
from .deps import JsonBody, clock_now, current_user
from .models import HOST_COLUMNS, Case, Client, Task, User, UserPrefs
from .rules import permissions_for, prepare
from .wire import legacy_item

router = APIRouter(tags=["tasks"])
WORK_DAY = WorkDay()


def prefs_source() -> StoredPreferences:
    return StoredPreferences(UserPrefs, WORK_DAY)


def viewer_zone(session: Any, user_id: str) -> str:
    return tasks.get_settings(session, UserPrefs, user_id, WORK_DAY).time_zone or "UTC"


def items(session: Any, rows: list[Any], user_id: str, now: Any) -> list[dict]:
    """Legacy items for `rows`: bond's item dict, then the app's keys with the client and case labels."""
    zone = viewer_zone(session, user_id)

    def names(ids: list[str]) -> dict[str, str]:
        return {u.id: u.name for u in session.query(User).filter(User.id.in_(ids))}

    base = tasks.task_items(rows, today=tasks.viewer_today(now, zone), now=now, names=names)
    clients = {c.id: c.name for c in session.query(Client)}
    cases = {c.id: c.label for c in session.query(Case)}
    return [legacy_item(item, row, client_name=clients.get(row.client_ref), case_label=cases.get(row.case_ref))
            for item, row in zip(base, rows, strict=True)]


def write_kwargs(session: Any, request: Request, user_id: str) -> dict:
    def user_exists(uid: str) -> bool:
        return session.get(User, uid) is not None

    return {"now": clock_now(request), "tz": "UTC", "prefs": prefs_source(), "user_exists": user_exists,
            "extras": None, "host_columns": HOST_COLUMNS, "prepare": prepare}


def _open(session: Any, task_id: str, user_id: str) -> Any:
    """The task, for a person who may see it: owner, assignee or admin (anyone else is 403 `not_task_editor`)."""
    task = tasks.get(session, Task, task_id)
    tasks.service.require_editor(task, user_id, permissions_for(session))
    return task


@router.post("/tasks", status_code=201)
def create_task(request: Request, body: JsonBody,
                user_id: str = Depends(current_user)) -> dict:
    data, extras = split(body, TaskCreate)
    with session_scope(request.app.state.session_factory) as session:
        kwargs = write_kwargs(session, request, user_id)
        kwargs["extras"] = extras
        task = tasks.create(session, task_model=Task, owner_user_id=user_id, actor_user_id=user_id, data=data,
                            **kwargs)
        return items(session, [task], user_id, clock_now(request))[0]


@router.get("/tasks")
def list_tasks(request: Request, status: str = Query("open", pattern="^(open|done|cancelled|active|all)$"),
               limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0),
               user_id: str = Depends(current_user)) -> dict:
    now = clock_now(request)
    with session_scope(request.app.state.session_factory) as session:
        rows, total = tasks.list_tasks(session, task_model=Task, user_id=user_id, filters=TaskFilters(status=status),
                                       limit=limit, offset=offset, viewer_zone=viewer_zone(session, user_id), now=now)
        return {"items": items(session, rows, user_id, now), "total": total}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request, user_id: str = Depends(current_user)) -> dict:
    with session_scope(request.app.state.session_factory) as session:
        return items(session, [_open(session, task_id, user_id)], user_id, clock_now(request))[0]


@router.put("/tasks/{task_id}")
def update_task(task_id: str, request: Request, body: JsonBody,
                user_id: str = Depends(current_user)) -> dict:
    data, extras = split(body, TaskUpdate)
    with session_scope(request.app.state.session_factory) as session:
        kwargs = write_kwargs(session, request, user_id)
        kwargs["extras"] = extras
        task = tasks.update(session, task=tasks.get(session, Task, task_id), actor_user_id=user_id, data=data,
                            permissions=permissions_for(session), **kwargs)
        return items(session, [task], user_id, clock_now(request))[0]


def _status_route(change: Any, name: str) -> None:
    @router.post(f"/tasks/{{task_id}}/{name}", name=f"{name}_task")
    def handler(task_id: str, request: Request, user_id: str = Depends(current_user)) -> dict:
        with session_scope(request.app.state.session_factory) as session:
            now = clock_now(request)
            task = change(session, tasks.get(session, Task, task_id), user_id, now,
                          permissions=permissions_for(session))
            return items(session, [task], user_id, now)[0]


_status_route(tasks.complete, "complete")
_status_route(tasks.reopen, "reopen")


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, request: Request, user_id: str = Depends(current_user)) -> Response:
    with session_scope(request.app.state.session_factory) as session:
        tasks.delete(session, tasks.get(session, Task, task_id), user_id, permissions=permissions_for(session))
    return Response(status_code=204)

