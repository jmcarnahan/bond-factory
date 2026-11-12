"""Sync routes for apps that sync ``notices`` to devices.

``notice_routes(notice_model, now=...)`` returns ``{("notices", None): NoticeRoute}``. ``NoticeRoute`` has the same
three fields as the sync lib's ``Route`` (``ops``, ``handler``, ``reads``) and the handler signature
``handler(session, ctx, op, data)``; the app wraps it. This lib does not import the sync lib; refusals raise
``NoticeError``. The device may write only ``read_at`` and ``dismissed_at`` (patch); the server owns the rest.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bond_notify_py.errors import NoticeError
from bond_notify_py.timeutil import to_naive_utc, utcnow

#: What a device may write.
FIELDS = ("read_at", "dismissed_at")


@dataclass(frozen=True)
class NoticeRoute:
    ops: frozenset
    handler: Callable
    reads: tuple = ()


def actor_of(ctx: Any) -> str:
    """``ctx.user`` is the session user id (a string) or an object with ``user_id`` / ``id``."""
    user = ctx.user
    if isinstance(user, str):
        return user
    return getattr(user, "user_id", None) or user.id


def verdict_for(exc: Exception) -> tuple[str, str] | None:
    """``(sync verdict code, message)`` for a ``NoticeError``, else None; the coded name is the message."""
    if not isinstance(exc, NoticeError):
        return None
    code = {403: "forbidden", 404: "not_found", 409: "conflict"}.get(exc.status, "invalid")
    return code, exc.code


def notice_routes(notice_model: Any, now: Callable = utcnow) -> dict:
    """Routes bound to ``notice_model``: ``("notices", None)`` patch of ``read_at`` / ``dismissed_at``.

    A non-null value from the device means "mark it now": the server's ``now`` is stored, never the device's clock,
    and a stamp already set keeps its first value. A null clears nothing. Dismissing also reads. Only the
    user's own rows may be touched; put and delete are not offered."""

    def patch(session: Any, ctx: Any, op: Any, data: dict) -> None:
        row = session.get(notice_model, op.id)
        if row is None:
            raise NoticeError("notice_not_found")
        if row.user_id != actor_of(ctx):
            raise NoticeError("not_notice_owner")
        stamp = to_naive_utc(now())
        if data.get("read_at") is not None and row.read_at is None:
            row.read_at = stamp
        if data.get("dismissed_at") is not None:
            if row.dismissed_at is None:
                row.dismissed_at = stamp
            if row.read_at is None:
                row.read_at = stamp
        session.flush()

    return {("notices", None): NoticeRoute(frozenset({"patch"}), patch, FIELDS)}
