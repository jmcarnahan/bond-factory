"""Declarative mixin for the ``tasks`` table.

    class Task(TasksMixin, Base): ...

The mixin owns the table name, the columns and the two list indexes. Datetimes are naive UTC; ``due_date`` is a
calendar date and ``due_time`` a local wall-clock ``HH:MM`` string (never a DateTime). The lib ships no migration:
the app's own revision creates the table (``TASK_COLUMNS`` is the contract a test can assert against).
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import declared_attr

NO_REMINDER = -2
MORNING_OF = -1
USE_DEFAULT_REMINDER = -3


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class MirrorStatus(StrEnum):
    PENDING = "pending"
    MIRRORED = "mirrored"
    SKIPPED = "skipped"
    FAILED = "failed"


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


#: column name -> nullable. The literal contract of the ``tasks`` table; tests pin it.
TASK_COLUMNS: dict[str, bool] = {
    "id": False,
    "owner_user_id": False,
    "created_by": False,
    "assigned_user_id": True,
    "title": False,
    "notes": True,
    "due_date": True,
    "due_time": True,
    "priority": True,
    "due_at": True,
    "status": False,
    "completed_at": True,
    "completed_by": True,
    "checklist": False,
    "remind_minutes_before": False,
    "mirror_enabled": False,
    "mirror_status": False,
    "external_provider": True,
    "external_event_id": True,
    "external_account_user_id": True,
    "external_etag": True,
    "links": False,
    "source": False,
    "created_at": False,
    "updated_at": False,
}


class TasksMixin:
    __tablename__ = "tasks"

    @declared_attr.directive
    def __table_args__(cls):
        return (
            Index("ix_tasks_owner_status_due", "owner_user_id", "status", "due_date"),
            Index("ix_tasks_assignee_status_due", "assigned_user_id", "status", "due_date"),
            Index("ix_tasks_status_due_at", "status", "due_at"),
        )

    id = Column(String, primary_key=True, default=_uuid)
    owner_user_id = Column(String, nullable=False, index=True)
    created_by = Column(String, nullable=False)
    assigned_user_id = Column(String, nullable=True, index=True)
    title = Column(String(255), nullable=False)
    notes = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True, index=True)
    due_time = Column(String(5), nullable=True)  # "HH:MM" local wall clock; needs due_date
    priority = Column(Integer, nullable=True)  # 1 low, 2 normal, 3 high, null not set
    due_at = Column(DateTime, nullable=True)  # server-computed due instant, naive UTC, minute precision
    status = Column(String, nullable=False, default=TaskStatus.OPEN.value)
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(String, nullable=True)
    checklist = Column(JSON, nullable=False, default=list)  # [{id, text, done_at|None}]
    # -3 my default, -2 none, -1 morning of the due date, N minutes before
    remind_minutes_before = Column(Integer, nullable=False, default=USE_DEFAULT_REMINDER)
    mirror_enabled = Column(Boolean, nullable=False, default=True)
    mirror_status = Column(String, nullable=False, default=MirrorStatus.PENDING.value)
    external_provider = Column(String, nullable=True)  # "google" | "microsoft"
    external_event_id = Column(String, nullable=True)
    external_account_user_id = Column(String, nullable=True)  # the mailbox that holds the event
    external_etag = Column(String, nullable=True)
    links = Column(JSON, nullable=False, default=list)  # [{kind, id, label}]
    source = Column(String, nullable=False, default="manual")
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
