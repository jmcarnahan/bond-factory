"""Sync routes for apps that sync ``push_devices`` (the device writes its own row).

``device_routes(device_model, now=...)`` returns ``{("push_devices", None): DeviceRoute}``. ``DeviceRoute`` has the
same three fields as the sync lib's ``Route`` (``ops``, ``handler``, ``reads``) and the handler signature
``handler(session, ctx, op, data)``; the app wraps it. This lib does not import the sync lib; refusals raise
``PushError``.

A device may write ``token``, ``platform``, ``environment``, ``topic`` and ``device_id`` on insert, and only
``token`` on update. ``user_id`` (from ``ctx.user``, never the client's), ``last_seen_at`` (the clock),
``disabled_at`` and ``created_at`` are server-owned. A token or (user, device) collision becomes a coded
``PushError``, never a database error; a token held by another row moves (see ``register_device``).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bond_push_py.timeutil import utcnow

#: What a device may write on insert. On update only ``token`` is writable (``UPDATE_FIELDS``).
FIELDS = ("token", "platform", "environment", "topic", "device_id")
UPDATE_FIELDS = ("token",)


@dataclass(frozen=True)
class DeviceRoute:
    ops: frozenset
    handler: Callable
    reads: tuple = ()


def device_routes(device_model: Any, now: Callable = utcnow) -> dict:
    """Routes bound to ``device_model``: ``("push_devices", None)`` put (insert, via ``register_device``), patch
    (``token`` only; ``last_seen_at`` is set from ``now()``) and delete (via ``unregister_device``). The row's
    ``user_id`` is always the session user; a put or patch cannot touch another user's row."""
    raise NotImplementedError("sync_routes.device_routes is not implemented yet")
