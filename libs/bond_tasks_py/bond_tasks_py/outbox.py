"""Notice outbox: one row per (ledger row, external channel), inserted in the claim's transaction. The inbox has no
outbox row: its notice is written in the claim itself. Delivery is at-least-once; every channel must be
idempotent on ``notice_id``."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import declared_attr

from bond_tasks_py.notify_protocols import Notifier

#: column name -> nullable. The literal contract of ``task_notice_outbox``; tests pin it.
TASK_NOTICE_OUTBOX_COLUMNS: dict[str, bool] = {
    "ledger_id": False,
    "channel": False,
    "delivered_at": True,
    "failed_at": True,
    "attempts": False,
    "last_error": True,
    "lease_until": True,
    "created_at": False,
}


class NoticeOutboxMixin:
    __tablename__ = "task_notice_outbox"

    @declared_attr.directive
    def __table_args__(cls):
        return (Index("ix_task_notice_outbox_pending", "failed_at", "delivered_at", "lease_until"),)

    ledger_id = Column(String(32), primary_key=True)
    channel = Column(String(32), primary_key=True)
    delivered_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)  # given up, or the target is unregistered
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False)


@dataclass(frozen=True)
class DeliverResult:
    leased: int = 0
    sent: int = 0
    retryable: int = 0
    unregistered: int = 0
    failed: int = 0  # permanent verdict, or gave up after ``max_attempts``


def deliver_pending(session: Any, *, ledger_model: Any, outbox_model: Any, notifiers: Mapping[str, Notifier],
                    now: datetime, commit: Callable[[], None], limit: int = 100, lease_seconds: int = 300,
                    max_attempts: int = 5) -> DeliverResult:
    """Send the pending outbox rows, at least once.

    Pending means ``delivered_at IS NULL AND failed_at IS NULL AND (lease_until IS NULL OR lease_until < now)``.
    The rows are leased with one compare-and-set UPDATE, and ``commit()`` is called straight after it: the lease
    must be committed before any send, so other workers see it and no database lock is held during a network
    call. Each result is stamped and ``commit()`` is called again. A notifier returns "ok" (stamp
    ``delivered_at``), "retryable" (keep the row for a later lease; after ``max_attempts`` it counts as failed),
    "unregistered" (stamp ``failed_at``: the target is gone) or "failed" (permanent: stamp ``failed_at`` at once).
    A crash between a send and its stamp sends again after the lease ends, so every channel must be idempotent on
    ``notice_id``."""
    raise NotImplementedError("outbox.deliver_pending is not implemented yet")
