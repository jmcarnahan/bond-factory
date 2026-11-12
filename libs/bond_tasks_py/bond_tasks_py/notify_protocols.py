"""Seams of the notification pipeline (frozen). Notifiers in other libs read ``Notice`` by attribute only and
never import it; the shapes meet by structure.

``TransactionalNotifier.write`` runs inside the claim (the inbox); ``Notifier.send`` runs after commit from the
outbox (push, chat, email).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from bond_tasks_py.protocols import UserPrefs

STAGES = ("close", "due", "past")
NOTICE_ACTIONS = ("done", "snooze", "cancel")
NOTICE_CATEGORY = "bond.task"  # the base notification category on the phone; "<this>.owner" also offers Cancel


@dataclass(frozen=True)
class Notice:
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
    actions: tuple[str, ...]  # subset of NOTICE_ACTIONS, by the recipient's permissions
    last: bool  # True on the final past-due notice


class TransactionalNotifier(Protocol):
    def write(self, session: Any, notices: Sequence[Any]) -> None: ...  # raises to cancel the batch's claim


class Notifier(Protocol):
    def send(self, session: Any, notice: Any) -> str:
        """One of "ok", "retryable" (try again later), "unregistered" (the target is gone) or "failed" (a
        permanent refusal: do not retry)."""
        ...


class Recipients(Protocol):
    def for_stage(self, session: Any, task: Any, stage: str) -> list[str]: ...


# (task, stage, seq, prefs) -> (title, body). `last` is not passed: compare seq with the max_past given to sweep_due.
Compose = Callable[[Any, str, int, UserPrefs], tuple[str, str]]
