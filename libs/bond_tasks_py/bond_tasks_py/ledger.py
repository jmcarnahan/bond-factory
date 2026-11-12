"""Notice ledger: one row per claimed (or skipped) notice. The claim is an insert; the unique key is what makes
a notice exactly-once across workers. ``deadline_token`` is never null (a null in a unique key removes
uniqueness)."""

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import declared_attr

#: column name -> nullable. The literal contract of ``task_notice_ledger``; tests pin it.
TASK_NOTICE_LEDGER_COLUMNS: dict[str, bool] = {
    "id": False,
    "task_id": False,
    "user_id": False,
    "stage": False,
    "seq": False,
    "deadline_token": False,
    "status": False,
    "stage_at": False,
    "payload": False,
    "claimed_at": False,
}


class NoticeLedgerMixin:
    __tablename__ = "task_notice_ledger"

    @declared_attr.directive
    def __table_args__(cls):
        return (
            UniqueConstraint("task_id", "user_id", "stage", "seq", "deadline_token", name="uq_task_notice_ledger_key"),
            Index("ix_task_notice_ledger_task_id", "task_id"),
            Index("ix_task_notice_ledger_claimed_at", "claimed_at"),
        )

    id = Column(String(32), primary_key=True)  # = notice_id
    task_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    stage = Column(String(8), nullable=False)  # close | due | past
    seq = Column(Integer, nullable=False)
    deadline_token = Column(String(32), nullable=False)
    status = Column(String(8), nullable=False)  # claimed | skipped
    stage_at = Column(DateTime, nullable=False)
    payload = Column(JSON, nullable=False)  # kind, title, body, due_at, priority, route
    claimed_at = Column(DateTime, nullable=False)
