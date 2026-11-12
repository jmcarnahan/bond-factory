"""Device registry services. Every function takes a session, flushes, and never commits. ``now`` is naive UTC.

Refusals raise ``PushError``.
"""

from datetime import datetime
from typing import Any


def register_device(session: Any, device_model: Any, *, user_id: str, device_id: str, token: str, platform: str,
                    environment: str, topic: str | None, now: datetime) -> Any:
    """Upsert by (user_id, device_id): new token and ``last_seen_at``, clears ``disabled_at``. A token already
    held by another row (another device or user: a phone changed hands) moves: the old row is deleted, then
    this one is written, in one flush, so the unique token never collides. Invalid input (platform,
    environment, empty token or device id) is a coded ``PushError``, never a database error. Returns the row."""
    raise NotImplementedError("devices.register_device is not implemented yet")


def unregister_device(session: Any, device_model: Any, *, user_id: str, device_id: str) -> bool:
    """Delete the row; True if one existed. Deleting what is gone is success."""
    raise NotImplementedError("devices.unregister_device is not implemented yet")


def devices_for(session: Any, device_model: Any, user_id: str) -> list:
    """The user's live rows (``disabled_at`` null), newest ``last_seen_at`` first."""
    raise NotImplementedError("devices.devices_for is not implemented yet")
