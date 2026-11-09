"""Sync routes for apps that sync ``tasks`` to devices.

``sync_routes(task_model, ...)`` returns ``{(table, action): TaskRoute}``. ``TaskRoute`` has the same three fields as the
sync lib's ``Route`` (``ops``, ``handler``, ``reads``), and each handler has its signature ``handler(session, ctx,
op, data)``: the app wraps them (``Route(r.ops, r.handler, r.reads)``). This lib does not import the sync lib, so the
handlers raise ``TaskError``; map it with ``verdict_for`` in the host's ``reject_for`` hook.

Routes: ``("tasks", None)`` put / patch / delete, ``("tasks", "complete")`` and ``("tasks", "reopen")``.
``ctx.user`` is the session user id (a string) or an object with ``user_id`` / ``id``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bond_tasks_py import service
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import MirrorPointer, Scheduler
from bond_tasks_py.reminders import cancel_reminder, schedule_reminder
from bond_tasks_py.schema import TaskCreate, TaskUpdate
from bond_tasks_py.timeutil import utcnow

#: What a device may write. Owner, created_by, completed_*, mirror_* and external_* are server-owned.
FIELDS = ("title", "notes", "due_date", "due_time", "assigned_user_id", "remind_minutes_before", "mirror_enabled",
          "checklist", "links")
BLANK_IS_NONE = ("notes", "due_date", "due_time", "assigned_user_id")
READS = FIELDS + ("status",)


@dataclass(frozen=True)
class TaskRoute:
    ops: frozenset
    handler: Callable
    reads: tuple = ()


def actor_of(ctx: Any) -> str:
    user = ctx.user
    if isinstance(user, str):
        return user
    return getattr(user, "user_id", None) or user.id


def _fields(data: dict) -> dict:
    out = {}
    for key in FIELDS:
        if key in data:
            value = data[key]
            out[key] = None if key in BLANK_IS_NONE and value == "" else value
    return out


def verdict_for(exc: Exception) -> tuple[str, str] | None:
    """``(sync verdict code, message)`` for a ``TaskError``, else None. Refusals use the sync vocabulary
    (forbidden, not_found, conflict, invalid); the coded name is the message so a device can show it."""
    if not isinstance(exc, TaskError):
        return None
    code = {403: "forbidden", 404: "not_found", 409: "conflict"}.get(exc.status, "invalid")
    return code, exc.code


def sync_routes(task_model: Any, *, now: Callable = utcnow, tz: str = "UTC",
                user_exists: Callable[[str], bool] | None = None, scheduler: Scheduler | None = None,
                after_write: Callable[[Any, Any, Any], None] | None = None,
                after_delete: Callable[[Any, Any, MirrorPointer | None], None] | None = None) -> dict:
    """Routes bound to ``task_model``. ``scheduler`` (optional) keeps reminders in step. ``after_write(ctx, session,
    task)`` and ``after_delete(ctx, session, pointer)`` let the app start the mirror after the op commits (for
    example ``ctx.background.add_task``)."""

    def changed(ctx: Any, session: Any, task: Any) -> None:
        if scheduler is not None:
            schedule_reminder(session, task, scheduler, tz=tz)
        if after_write is not None:
            after_write(ctx, session, task)

    def put(session: Any, ctx: Any, op: Any, data: dict) -> None:
        owner = actor_of(ctx)
        existing = session.get(task_model, op.id)
        if existing is not None and existing.owner_user_id == owner:
            return  # a replay of a create the server already has
        body = {k: v for k, v in _fields(data).items() if v is not None}
        task = service.create(session, task_model=task_model, owner_user_id=owner, actor_user_id=owner,
                              data=TaskCreate(id=op.id, **body), now=now(), tz=tz, user_exists=user_exists)
        changed(ctx, session, task)

    def patch(session: Any, ctx: Any, op: Any, data: dict) -> None:
        actor = actor_of(ctx)
        task = service.get(session, task_model, op.id)
        status = data.get("status")
        if status not in (None, "open", "done"):  # before any write
            raise ValueError("status must be open or done")
        fields = _fields(data)
        if fields:
            task = service.update(session, task=task, actor_user_id=actor, data=TaskUpdate(**fields), now=now(),
                                  tz=tz, user_exists=user_exists)
        if status == "done":
            task = service.complete(session, task, actor, now())
        elif status == "open":
            task = service.reopen(session, task, actor, now())
        if fields or status:
            changed(ctx, session, task)

    def delete(session: Any, ctx: Any, op: Any, data: dict) -> None:
        task = session.get(task_model, op.id)
        if task is None:
            return  # deleting what is already gone is success
        pointer = service.delete(session, task, actor_of(ctx))
        if scheduler is not None:
            cancel_reminder(session, op.id, scheduler)
        if after_delete is not None:
            after_delete(ctx, session, pointer)

    def complete(session: Any, ctx: Any, op: Any, data: dict) -> None:
        task = service.complete(session, service.get(session, task_model, op.id), actor_of(ctx), now())
        changed(ctx, session, task)

    def reopen(session: Any, ctx: Any, op: Any, data: dict) -> None:
        task = service.reopen(session, service.get(session, task_model, op.id), actor_of(ctx), now())
        changed(ctx, session, task)

    return {
        ("tasks", None): TaskRoute(frozenset({"put", "patch", "delete"}), _dispatch(put, patch, delete), READS),
        ("tasks", "complete"): TaskRoute(frozenset({"put", "patch"}), complete),
        ("tasks", "reopen"): TaskRoute(frozenset({"put", "patch"}), reopen),
    }


def _dispatch(put: Callable, patch: Callable, delete: Callable) -> Callable:
    handlers = {"put": put, "patch": patch, "delete": delete}

    def handler(session: Any, ctx: Any, op: Any, data: dict) -> None:
        return handlers[op.op](session, ctx, op, data)

    return handler
