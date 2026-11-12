"""The sender seam, and what this lib reads from a notice (it never imports the class)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from bond_push_py.messages import PushMessage, PushResult


class PushSender(Protocol):
    """Sends a batch; returns one ``PushResult`` per message, in order. Never raises for a bad token."""

    def send(self, messages: Sequence[PushMessage]) -> list[PushResult]: ...


class NoticeLike(Protocol):
    """Documentation type for the notice ``PushNotifier.send`` receives (the tasks lib's ``Notice`` matches it)."""

    notice_id: str
    task_id: str
    user_id: str
    stage: str
    seq: int
    kind: str
    title: str
    body: str
    due_at: datetime | None
    priority: int | None
    route: str | None
    created_at: datetime
    actions: tuple[str, ...]
    last: bool
