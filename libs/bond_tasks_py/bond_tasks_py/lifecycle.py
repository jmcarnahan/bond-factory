"""Applying a notice action to its task, the same way on every path."""

from datetime import datetime
from typing import Any

from bond_tasks_py.protocols import Permissions


def apply_notice_action(session: Any, *, task: Any, action: str, actor_user_id: str, now: datetime,
                        permissions: Permissions | None = None) -> Any:
    """Done completes; cancel cancels (needs ``can_own``); snooze changes nothing. Returns the task."""
    raise NotImplementedError("lifecycle.apply_notice_action is not implemented yet")
