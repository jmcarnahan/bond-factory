"""What this lib reads from a notice. It never imports the class: any object with these attributes works."""

from datetime import datetime
from typing import Protocol


class NoticeLike(Protocol):
    """Documentation type for the notice a notifier receives (the tasks lib's ``Notice`` matches it).

    Signatures type the notice as ``Any``; this Protocol lists the attributes the lib reads.
    """

    notice_id: str
    task_id: str
    user_id: str
    stage: str  # "close" | "due" | "past"
    seq: int
    kind: str
    title: str
    body: str
    due_at: datetime | None
    priority: int | None
    route: str | None
    created_at: datetime
    actions: tuple[str, ...]  # subset of ("done", "snooze", "cancel")
    last: bool
