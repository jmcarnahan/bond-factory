"""Declarative mixin for the ``notices`` table (the stored inbox).

    class Notice(NoticesMixin, Base): ...

The table must live in the same database as ``tasks``: the inbox row is written inside the sweep's claim. The lib
ships no migration; ``NOTICE_COLUMNS`` is the contract a test pins. Datetimes are naive UTC.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Index, String, Text
from sqlalchemy.orm import declared_attr


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


#: column name -> nullable. The literal contract of the ``notices`` table; tests pin it.
NOTICE_COLUMNS: dict[str, bool] = {
    "id": False,
    "user_id": False,
    "kind": False,
    "title": False,
    "body": False,
    "data": False,
    "source_id": True,
    "created_at": False,
    "read_at": True,
    "dismissed_at": True,
}


class NoticesMixin:
    __tablename__ = "notices"

    @declared_attr.directive
    def __table_args__(cls):
        return (Index("ix_notices_user_created", "user_id", "created_at"),)

    id = Column(String(32), primary_key=True, default=_uuid)  # the notice id (sha256 prefix) on the task path
    user_id = Column(String, nullable=False)
    kind = Column(String(32), nullable=False)  # "task_due"
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    # task_id, stage, seq, due_at, priority, route, actions, last
    data = Column(JSON, nullable=False, default=dict)
    source_id = Column(String, nullable=True, index=True)  # the task id: put a finished task's notices away together
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    read_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
