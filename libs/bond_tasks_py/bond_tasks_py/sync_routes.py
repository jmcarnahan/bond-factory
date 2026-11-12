"""Sync routes for apps that sync ``tasks`` to devices.

``sync_routes(task_model, ...)`` returns ``{(table, action): TaskRoute}``. ``TaskRoute`` has the same three fields as the
sync lib's ``Route`` (``ops``, ``handler``, ``reads``), and each handler has its signature ``handler(session, ctx,
op, data)``: the app wraps them (``Route(r.ops, r.handler, r.reads)``). This lib does not import the sync lib, so the
handlers raise ``TaskError``; map it with ``verdict_for`` in the host's ``reject_for`` hook.

Routes: ``("tasks", None)`` put / patch / delete, ``("tasks", "complete")``, ``("tasks", "reopen")`` and
``("tasks", "cancel")``. A device's ``due_at`` is only a hint: a malformed one is dropped, never raised (a raise is
a permanent verdict on the device).
``ctx.user`` is the session user id (a string) or an object with ``user_id`` / ``id``.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from bond_tasks_py import service
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import AfterWrite, MirrorPointer, Permissions
from bond_tasks_py.schema import TaskCreate, TaskUpdate
from bond_tasks_py.timeutil import parse_iso, utcnow

#: What a device may write. Owner, created_by, completed_*, mirror_* and external_* are server-owned.
FIELDS = ("title", "notes", "due_date", "due_time", "priority", "due_at", "assigned_user_id",
          "remind_minutes_before", "mirror_enabled", "checklist", "links", "source")
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


def _allowed(fields: Collection[str] | None) -> tuple[str, ...]:
    if fields is None:
        return FIELDS
    unknown = sorted(set(fields) - set(FIELDS))
    if unknown:
        raise ValueError(f"not device-writable task fields: {', '.join(unknown)}")
    return tuple(k for k in FIELDS if k in set(fields))


def _fields(data: dict, allowed: Collection[str] = FIELDS) -> dict:
    out = {}
    for key in allowed:
        if key in data:
            value = data[key]
            out[key] = None if key in BLANK_IS_NONE and value == "" else value
    if "due_at" in out:  # only a hint: unreadable or null is dropped, never raised
        try:
            hint = parse_iso(out["due_at"])
        except (TypeError, ValueError, OverflowError):
            hint = None
        if hint is None:
            del out["due_at"]
        else:
            out["due_at"] = hint
    return out


def verdict_for(exc: Exception) -> tuple[str, str] | None:
    """``(sync verdict code, message)`` for a ``TaskError``, else None. Refusals use the sync vocabulary
    (forbidden, not_found, conflict, invalid); the coded name is the message so a device can show it."""
    if not isinstance(exc, TaskError):
        return None
    code = {403: "forbidden", 404: "not_found", 409: "conflict"}.get(exc.status, "invalid")
    return code, exc.code


def _checked(model: type, **fields: Any) -> Any:
    """Build ``TaskCreate`` / ``TaskUpdate``; a priority outside 1 to 3 is ``invalid_priority``, not a bare 422."""
    try:
        return model(**fields)
    except ValidationError as exc:
        if any(err["loc"] and err["loc"][0] == "priority" for err in exc.errors()):
            raise TaskError("invalid_priority") from exc
        raise


def sync_routes(task_model: Any, *, now: Callable = utcnow, tz: str = "UTC",
                user_exists: Callable[[str], bool] | None = None,
                after_write: Callable[[Any, Any, Any], None] | None = None,
                after_delete: Callable[[Any, Any, MirrorPointer | None], None] | None = None,
                zone_of: Callable[[Any, Any, str], str | None] | None = None, prefs: Any = None,
                permissions: Permissions | None = None, host_columns: Collection[str] = (),
                link_hook: AfterWrite | None = None, link_index_model: Any = None,
                on_deleted: Callable[[Any, Any, str, str], None] | None = None,
                prepare: Callable[[Any, Any | None, str, dict], dict] | None = None,
                fields: Collection[str] | None = None) -> dict:
    """Routes bound to ``task_model``. ``after_write(ctx, session,
    task)`` and ``after_delete(ctx, session, pointer)`` let the app start the mirror after the op commits (for
    example ``ctx.background.add_task``). ``zone_of(ctx, session, user_id)`` supplies the writer's stored zone (sync
    carries none per write), ``prefs`` and ``permissions`` are passed to the service, ``host_columns`` names the app
    columns a device may write and read, and ``link_hook(session, task)`` runs inside the service after each write.
    ``link_index_model`` (optional) has a deleted task's link index rows removed with it. ``on_deleted(ctx, session,
    task_id, owner_user_id)`` runs after each real delete, mirrored or not (for example to put away its notices). ``prepare(session, task or None, actor, extras)`` is passed to the
    service on put and patch (see ``service.create``). ``fields`` narrows what a device may write to those names
    of ``FIELDS``; a write of any other field is dropped, as an unknown field is today (None = all of ``FIELDS``);
    a name outside ``FIELDS`` raises ``ValueError``."""
    host = tuple(host_columns)
    allowed = _allowed(fields)
    reads = tuple(k for k in FIELDS if k in allowed) + ("status",) + host

    def changed(ctx: Any, session: Any, task: Any) -> None:
        if after_write is not None:
            after_write(ctx, session, task)

    def writer_zone(ctx: Any, session: Any, user: str) -> str | None:
        return zone_of(ctx, session, user) if zone_of is not None else None

    def extras_of(data: dict) -> dict:
        return {key: data[key] for key in host if key in data}

    def write_kwargs(ctx: Any, session: Any, actor: str, data: dict) -> dict:
        return {"now": now(), "tz": tz, "user_exists": user_exists, "writer_zone": writer_zone(ctx, session, actor),
                "prefs": prefs, "extras": extras_of(data), "host_columns": host, "after_write": link_hook, "prepare": prepare}

    def put(session: Any, ctx: Any, op: Any, data: dict) -> None:
        owner = actor_of(ctx)
        existing = session.get(task_model, op.id)
        if existing is not None and existing.owner_user_id == owner:
            return  # a replay of a create the server already has
        body = {k: v for k, v in _fields(data, allowed).items() if v is not None}
        task = service.create(session, task_model=task_model, owner_user_id=owner, actor_user_id=owner,
                              data=_checked(TaskCreate, id=op.id, **body), **write_kwargs(ctx, session, owner, data))
        changed(ctx, session, task)

    def patch(session: Any, ctx: Any, op: Any, data: dict) -> None:
        actor = actor_of(ctx)
        task = service.get(session, task_model, op.id)
        status = data.get("status")
        if status not in (None, "open", "done"):  # before any write
            raise ValueError("status must be open or done")
        fields, extras = _fields(data, allowed), extras_of(data)
        fields.pop("source", None)  # set when the task is created, never changed by a patch
        if set(fields) == {"due_at"}:
            fields = {}  # a lone hint changes nothing: no write, no resync
        if fields or extras:
            task = service.update(session, task=task, actor_user_id=actor, data=_checked(TaskUpdate, **fields),
                                  permissions=permissions, **write_kwargs(ctx, session, actor, data))
        if status == "done":
            task = service.complete(session, task, actor, now(), permissions=permissions)
        elif status == "open":
            task = service.reopen(session, task, actor, now(), permissions=permissions)
        if fields or extras or status:
            changed(ctx, session, task)

    def delete(session: Any, ctx: Any, op: Any, data: dict) -> None:
        task = session.get(task_model, op.id)
        if task is None:
            return  # deleting what is already gone is success
        owner = task.owner_user_id
        pointer = service.delete(session, task, actor_of(ctx), permissions=permissions,
                                 link_index_model=link_index_model)
        if on_deleted is not None:
            on_deleted(ctx, session, op.id, owner)
        if after_delete is not None:
            after_delete(ctx, session, pointer)

    def lifecycle_route(change: Callable) -> Callable:
        def handler(session: Any, ctx: Any, op: Any, data: dict) -> None:
            task = change(session, service.get(session, task_model, op.id), actor_of(ctx), now(),
                          permissions=permissions)
            changed(ctx, session, task)

        return handler

    return {
        ("tasks", None): TaskRoute(frozenset({"put", "patch", "delete"}), _dispatch(put, patch, delete), reads),
        ("tasks", "complete"): TaskRoute(frozenset({"put", "patch"}), lifecycle_route(service.complete)),
        ("tasks", "reopen"): TaskRoute(frozenset({"put", "patch"}), lifecycle_route(service.reopen)),
        ("tasks", "cancel"): TaskRoute(frozenset({"put", "patch"}), lifecycle_route(service.cancel)),
    }


def _dispatch(put: Callable, patch: Callable, delete: Callable) -> Callable:
    handlers = {"put": put, "patch": patch, "delete": delete}

    def handler(session: Any, ctx: Any, op: Any, data: dict) -> None:
        return handlers[op.op](session, ctx, op, data)

    return handler
