"""Sync routes for apps that sync ``notices`` to devices.

``notice_routes(notice_model, now=...)`` returns ``{("notices", None): NoticeRoute}``. ``NoticeRoute`` has the same
three fields as the sync lib's ``Route`` (``ops``, ``handler``, ``reads``) and the handler signature
``handler(session, ctx, op, data)``; the app wraps it. This lib does not import the sync lib; refusals raise
``NoticeError``. The device may write only ``read_at`` and ``dismissed_at`` (patch); the server owns the rest.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bond_notify_py.timeutil import utcnow

#: What a device may write.
FIELDS = ("read_at", "dismissed_at")


@dataclass(frozen=True)
class NoticeRoute:
    ops: frozenset
    handler: Callable
    reads: tuple = ()


def notice_routes(notice_model: Any, now: Callable = utcnow) -> dict:
    """Routes bound to ``notice_model``: ``("notices", None)`` patch of ``read_at`` / ``dismissed_at``."""
    raise NotImplementedError("sync_routes.notice_routes is not implemented yet")
