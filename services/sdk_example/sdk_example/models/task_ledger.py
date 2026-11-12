"""The notice ledger (exactly-once claim) and the outbox (one row per external channel)."""

from bond_tasks_py import NoticeLedgerMixin, NoticeOutboxMixin

from ..db import Base


class TaskNoticeLedger(NoticeLedgerMixin, Base):
    """Table ``task_notice_ledger``."""


class TaskNoticeOutbox(NoticeOutboxMixin, Base):
    """Table ``task_notice_outbox``."""
