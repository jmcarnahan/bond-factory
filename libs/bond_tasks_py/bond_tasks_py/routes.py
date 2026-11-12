"""``make_tasks_router``: the task routes behind one call. Needs fastapi (extra ``http``); import it as
``bond_tasks_py.routes`` only. The package ``__init__`` never imports this file.

    GET    {prefix}                  list      GET {prefix}/summary   GET {prefix}/today
    GET    {prefix}/settings         PUT {prefix}/settings            (only with ``settings_model``)
    GET    {prefix}/{id}             POST {prefix}  (201)             PUT {prefix}/{id}
    POST   {prefix}/{id}/complete | /reopen | /cancel                 DELETE {prefix}/{id}  (204)
    PUT    {prefix}/{id}/checklist/{item_id}   {"done": bool}

A ``TaskError`` anywhere in a route (a dependency included) answers ``error_map(exc)`` or, by default,
``exc.status`` with ``{"detail": {"code", "message"}}``. Static paths are registered before ``/{id}``.

Include this router AFTER the app's own static ``/tasks/<name>`` routes (for example ``GET /tasks/export``): FastAPI
matches in registration order, so ``/{id}`` would otherwise answer them with 404 ``task_not_found``.
"""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict

from bond_tasks_py import lifecycle, queries, service, usersettings
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import Permissions, UserPrefs
from bond_tasks_py.queries import TaskFilters
from bond_tasks_py.routes_core import Core, check_body_fields, checked_answer
from bond_tasks_py.schema import TaskCreate, TaskUpdate
from bond_tasks_py.settings_schema import SettingsUpdate, settings_item
from bond_tasks_py.today import today as find_today

ErrorMap = Callable[[TaskError], tuple[int, Any]]


class ChecklistTick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool


def _route_class(error_map: ErrorMap | None) -> type[APIRoute]:
    def answer(exc: TaskError) -> tuple[int, Any]:
        if error_map is not None:
            return checked_answer(error_map, exc)
        return exc.status, {"detail": {"code": exc.code, "message": exc.message}}

    class GuardedRoute(APIRoute):
        def get_route_handler(self) -> Callable:
            inner = super().get_route_handler()

            async def handler(request: Request) -> Response:
                try:
                    return await inner(request)
                except TaskError as exc:
                    status, body = answer(exc)
                    return JSONResponse(status_code=status, content=body)

            return handler

    return GuardedRoute


async def _check_body(request: Request) -> None:
    try:
        body = await request.json()
    except ValueError:
        return  # not JSON: the normal body validation answers
    check_body_fields(body)


def make_tasks_router(
    *, task_model: Any, session_scope: Callable[[], AbstractContextManager[Any]], user_dep: Callable,
    now: Callable[[], datetime], settings_model: Any = None, link_index_model: Any = None,
    write_dep: Callable | None = None, read_all_dep: Callable[[Request], None] | None = None,
    zone_for: Callable[[str], str | None] | None = None, tz: str = "UTC", permissions: Permissions | None = None,
    prepare: Callable[[Any, Any | None, str, dict], dict] | None = None,
    extra_where_for: Callable[[Request, str], Sequence] | None = None,
    item_extras: Callable[[Any], Mapping[str, Any]] | None = None,
    labels: Callable[[Any, list[dict]], Mapping[tuple[str, str], str]] | None = None,
    after_write: Callable[[Any, Any, datetime, Any], None] | None = None,
    after_delete: Callable[[Any, str, datetime], None] | None = None,
    error_map: ErrorMap | None = None, prefix: str = "/tasks",
    # Added beyond the planned signature; each defaults to the behaviour without it.
    prefs: Any = None, defaults: UserPrefs | None = None,
    names: Callable[[Any, list[str]], dict[str, str]] | None = None,
    user_exists: Callable[[Any, str], bool] | None = None, link_hook: Callable[[Any, Any], None] | None = None,
    snapshot: Callable[[Any, str], Any] | None = None, after_commit: Callable[[Any, Any], None] | None = None,
    after_delete_commit: Callable[[Any, Any], None] | None = None,
    on_recomputed: Callable[[Any, Any, datetime | None, datetime], None] | None = None,
) -> APIRouter:
    """Mount with ``app.include_router``.

    ``session_scope()`` is a context manager factory (the ``bond_signin`` precedent): it opens the transaction, commits
    on exit and rolls back on an exception. ``user_dep`` is a dependency that returns the caller's user id.
    ``now()`` is naive UTC. ``write_dep`` is an extra dependency of every write route. ``read_all_dep(request)`` raises
    to refuse ``scope=all`` and reading a task you do not edit; with None both are refused with 403 ``forbidden``.
    ``extra_where_for(request, user_id)`` gives ``list_tasks(extra_where=)``: it narrows the LIST route (and its total)
    only, not ``/summary``, ``/today`` or ``/{id}``. It is not a visibility rule: use ``permissions`` and
    ``read_all_dep`` for that. ``error_map(exc)`` must return ``(status, body)``; any other return, or a raise, is a
    ``TypeError`` naming ``error_map`` (a 500). ``item_extras(task)`` is merged after the
    24 item keys and never overrides one. ``labels(session, links)``, ``names(session, ids)`` and
    ``user_exists(session, user_id)`` are session-bound versions of the lib seams. ``zone_for(user_id)`` is a stored
    zone when there is no ``settings_model``.
    Hooks: ``after_write(session, task, now, before)`` runs in the transaction after create, update and each status
    change (``before`` is what ``snapshot(session, task_id)`` returned before an update, else None); ``after_delete(
    session, task_id, now)`` after a delete; ``after_commit(background, task)`` and ``after_delete_commit(background,
    pointer)`` queue work on the response's BackgroundTasks; ``link_hook`` is the lib's ``AfterWrite``;
    ``on_recomputed(session, task, old_due_at, now)`` follows a settings change that moved a due instant.
    ``prefs`` is the ``Preferences`` for writes (default: ``StoredPreferences(settings_model, defaults)``);
    ``defaults`` the app's work day."""
    core = Core(task_model=task_model, settings_model=settings_model, link_index_model=link_index_model,
                session_scope=session_scope, now=now, zone_for=zone_for, tz=tz, permissions=permissions,
                prepare=prepare, item_extras=item_extras, labels=labels, names=names, user_exists=user_exists,
                prefs=prefs, defaults=defaults, link_hook=link_hook, after_write=after_write, snapshot=snapshot,
                after_commit=after_commit)
    router = APIRouter(prefix=prefix, route_class=_route_class(error_map), tags=["tasks"])
    write = [Depends(write_dep)] if write_dep is not None else []
    body_check = [Depends(_check_body)]
    model = task_model

    def need_read_all(request: Request) -> None:
        if read_all_dep is None:
            raise TaskError("forbidden", "Reading other people's tasks is not allowed.", 403)
        read_all_dep(request)

    @router.get("")
    def list_tasks(
        request: Request, user_id: str = Depends(user_dep), scope: str = Query("mine", pattern="^(mine|all)$"),
        status: str = Query("open", pattern="^(open|done|cancelled|active|all)$"), time_zone: str | None = None,
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
            need_read_all(request)
        where = list(extra_where_for(request, user_id)) if extra_where_for is not None else []
        with session_scope() as session:
            zone = core.viewer_zone(session, user_id, time_zone)
            rows, total = queries.list_tasks(
                session, task_model=model, user_id=user_id, filters=filters, limit=limit, offset=offset,
                link_index_model=link_index_model, viewer_zone=zone, now=now(), extra_where=where)
            return {"items": core.items(session, rows, zone), "total": total, "limit": limit, "offset": offset}

    @router.get("/summary")
    def summary(time_zone: str | None = None, user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            zone = core.viewer_zone(session, user_id, time_zone)
            return queries.summary(session, task_model=model, user_id=user_id, now=now(), viewer_zone=zone)

    @router.get("/today")
    def today(time_zone: str | None = None, user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            zone = core.viewer_zone(session, user_id, time_zone)
            found = find_today(session, task_model=model, user_id=user_id, now=now(), viewer_zone=zone)
            return {"overdue": core.items(session, found.overdue, zone), "today": core.items(session, found.today, zone),
                    "undated": core.items(session, found.undated, zone),
                    "done_today": core.items(session, found.done_today, zone), "counts": dict(found.counts)}

    if settings_model is not None:
        @router.get("/settings")
        def get_settings(user_id: str = Depends(user_dep)) -> dict:
            with session_scope() as session:
                return settings_item(core.stored_prefs(session, user_id), (),
                                     usersettings.settings_overridden(session.get(settings_model, user_id)))

        @router.put("/settings", dependencies=body_check)
        def put_settings(body: SettingsUpdate, user_id: str = Depends(user_dep)) -> dict:
            with session_scope() as session:
                moment = now()

                def moved(task: Any, old_due_at: datetime | None) -> None:
                    if on_recomputed is not None:
                        on_recomputed(session, task, old_due_at, moment)

                found, warnings = usersettings.update_settings(
                    session, settings_model=settings_model, task_model=model, user_id=user_id, data=body, tz=tz,
                    now=moment, on_recomputed=moved, defaults=defaults)
                return settings_item(found, warnings, usersettings.settings_overridden(
                    session.get(settings_model, user_id)))

    @router.get("/{task_id}")
    def get_task(task_id: str, request: Request, time_zone: str | None = None,
                 user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            task = service.get(session, model, task_id)
            if not lifecycle.is_editor(task, user_id, permissions):
                need_read_all(request)
            return core.item(session, task, core.viewer_zone(session, user_id, time_zone))

    @router.post("", status_code=201, dependencies=[*body_check, *write])
    def create_task(body: TaskCreate, background: BackgroundTasks, time_zone: str | None = None,
                    user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            task = service.create(session, task_model=model, owner_user_id=user_id, actor_user_id=user_id, data=body,
                                  **core.write_kwargs(session, user_id))
            core.written(session, background, task)
            return core.item(session, task, core.viewer_zone(session, user_id, time_zone))

    @router.put("/{task_id}", dependencies=[*body_check, *write])
    def update_task(task_id: str, body: TaskUpdate, background: BackgroundTasks, time_zone: str | None = None,
                    user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            before = core.before(session, task_id)
            task = service.update(session, task=service.get(session, model, task_id), actor_user_id=user_id,
                                  data=body, permissions=permissions, **core.write_kwargs(session, user_id))
            core.written(session, background, task, before)
            return core.item(session, task, core.viewer_zone(session, user_id, time_zone))

    def status_route(change: Callable, name: str) -> None:
        @router.post(f"/{{task_id}}/{name}", name=f"{name}_task", dependencies=write)
        def handler(task_id: str, background: BackgroundTasks, time_zone: str | None = None,
                    user_id: str = Depends(user_dep)) -> dict:
            with session_scope() as session:
                task = change(session, service.get(session, model, task_id), user_id, now(), permissions=permissions)
                core.written(session, background, task)
                return core.item(session, task, core.viewer_zone(session, user_id, time_zone))

    status_route(service.complete, "complete")
    status_route(service.reopen, "reopen")
    status_route(service.cancel, "cancel")

    @router.delete("/{task_id}", status_code=204, dependencies=write)
    def delete_task(task_id: str, background: BackgroundTasks, user_id: str = Depends(user_dep)) -> Response:
        with session_scope() as session:
            pointer = service.delete(session, service.get(session, model, task_id), user_id,
                                     permissions=permissions, link_index_model=link_index_model)
            if after_delete is not None:
                after_delete(session, task_id, now())
        if pointer is not None and after_delete_commit is not None:
            after_delete_commit(background, pointer)
        return Response(status_code=204)

    @router.put("/{task_id}/checklist/{item_id}", dependencies=write)
    def tick_item(task_id: str, item_id: str, body: ChecklistTick, time_zone: str | None = None,
                  user_id: str = Depends(user_dep)) -> dict:
        with session_scope() as session:
            task = service.get(session, model, task_id)
            service.set_checklist_item(task, item_id, body.done, now(), actor_user_id=user_id,
                                       permissions=permissions)
            return core.item(session, task, core.viewer_zone(session, user_id, time_zone))

    return router
