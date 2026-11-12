"""The sender seam's value types."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PushMessage:
    """One push to one device token. ``collapse_id`` is the notice id (Apple ``apns-collapse-id``);
    ``category`` becomes the Apple ``category`` field, so the phone shows the action buttons registered under it
    (the tasks lib's ``NOTICE_CATEGORY``, "bond.task"). ``priority`` is the Apple ``apns-priority`` (10 or 5)."""

    token: str
    environment: str  # "sandbox" | "production"
    topic: str | None
    title: str
    body: str
    collapse_id: str | None = None
    data: dict = field(default_factory=dict)  # custom payload keys, e.g. {notice_id, task_id, route}
    expires_at: datetime | None = None  # naive UTC
    priority: int = 10
    thread_id: str | None = None
    category: str | None = None


@dataclass(frozen=True)
class PushResult:
    ok: bool
    unregistered: bool = False  # 410 or BadDeviceToken: stop sending to this token
    retryable: bool = False  # 429 or 5xx: try again later
    error: str | None = None
