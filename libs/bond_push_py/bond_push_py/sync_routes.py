"""Sync routes for apps that sync ``push_devices`` (the device writes its own row).

``device_routes(device_model, now=...)`` returns ``{("push_devices", None): DeviceRoute}``. ``DeviceRoute`` has the
same three fields as the sync lib's ``Route`` (``ops``, ``handler``, ``reads``) and the handler signature
``handler(session, ctx, op, data)``; the app wraps it. This lib does not import the sync lib; refusals raise
``PushError``, which ``verdict_for`` maps to a sync verdict.

A device may write ``token``, ``platform``, ``environment``, ``topic`` and ``device_id`` on insert, and the same
except ``device_id`` on update, validated as ``register_device`` validates them. ``user_id`` (from ``ctx.user``, never the client's), ``last_seen_at`` (the clock),
``disabled_at`` and ``created_at`` are server-owned. A token or (user, device) collision becomes a coded
``PushError``, never a database error; a token held by another row moves (see ``register_device``).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError

from bond_push_py.devices import check_fields, register_device, release_token, unregister_device
from bond_push_py.errors import PushError
from bond_push_py.timeutil import to_naive_utc, utcnow

#: What a device may write on insert. On update ``device_id`` is fixed; the rest are writable (``UPDATE_FIELDS``):
#: a debug build becomes a release build on the same device, so environment and token change together.
FIELDS = ("token", "platform", "environment", "topic", "device_id")
UPDATE_FIELDS = ("token", "platform", "environment", "topic")


@dataclass(frozen=True)
class DeviceRoute:
    ops: frozenset
    handler: Callable
    reads: tuple = ()


def actor_of(ctx: Any) -> str:
    user = ctx.user
    if isinstance(user, str):
        return user
    return getattr(user, "user_id", None) or user.id


def verdict_for(exc: Exception) -> tuple[str, str] | None:
    """``(sync verdict code, message)`` for a ``PushError``, else None (forbidden, not_found, conflict, invalid;
    the coded name is the message)."""
    if not isinstance(exc, PushError):
        return None
    code = {403: "forbidden", 404: "not_found", 409: "conflict"}.get(exc.status, "invalid")
    return code, exc.code


def device_routes(device_model: Any, now: Callable = utcnow) -> dict:
    """Routes bound to ``device_model``: ``("push_devices", None)`` put (insert, via ``register_device``), patch
    (``UPDATE_FIELDS``; ``last_seen_at`` is set from ``now()`` on every accepted write) and delete (via
    ``unregister_device``). The row's ``user_id`` is always the session user; a put or patch cannot touch another
    user's row. A put uses ``op.id`` as the id of a NEW row; if the user already has a row for that ``device_id``
    under another id (a row made before ``device_row_id`` existed), that row is updated and keeps ITS id, so
    there is never a second row for one device. Non-string input is a coded ``PushError``."""

    def owned(session: Any, owner: str, row_id: str) -> Any:
        row = session.get(device_model, row_id)
        if row is not None and row.user_id != owner:
            raise PushError("not_device_owner")
        return row

    def put(session: Any, ctx: Any, op: Any, data: dict) -> None:
        owner = actor_of(ctx)
        row = owned(session, owner, op.id)
        device_id = row.device_id if row is not None else data.get("device_id")  # a row's device id is fixed
        register_device(
            session, device_model, user_id=owner, device_id=device_id,
            token=data.get("token"), platform=data.get("platform"),
            environment=data.get("environment"), topic=data.get("topic") or None,
            now=now(), row_id=op.id,
        )

    def patch(session: Any, ctx: Any, op: Any, data: dict) -> None:
        row = owned(session, actor_of(ctx), op.id)
        if row is None:
            raise PushError("device_not_found")
        new = {k: (data[k] or None) if k == "topic" else data[k] for k in UPDATE_FIELDS if k in data}
        merged = {k: new.get(k, getattr(row, k)) for k in UPDATE_FIELDS}
        check_fields(**merged)
        for attempt in (1, 2):
            release_token(session, device_model, merged["token"], keep=row)
            try:
                with session.begin_nested():
                    for key, value in merged.items():
                        setattr(row, key, value)
                    row.last_seen_at = to_naive_utc(now())
                    row.disabled_at = None
                    session.flush()
                return
            except IntegrityError:  # a concurrent writer took the token: release it and try once more
                if attempt == 2:
                    raise PushError("device_conflict") from None

    def delete(session: Any, ctx: Any, op: Any, data: dict) -> None:
        row = owned(session, actor_of(ctx), op.id)
        if row is not None:  # gone already is success
            unregister_device(session, device_model, user_id=row.user_id, device_id=row.device_id)

    handlers = {"put": put, "patch": patch, "delete": delete}

    def handler(session: Any, ctx: Any, op: Any, data: dict) -> None:
        return handlers[op.op](session, ctx, op, data)

    return {("push_devices", None): DeviceRoute(frozenset({"put", "patch", "delete"}), handler, FIELDS)}
