"""Ledger and outbox retention: what may be deleted without causing a re-send."""

from datetime import datetime
from typing import Any


def prune_ledger(session: Any, *, task_model: Any, ledger_model: Any, outbox_model: Any, now: datetime,
                 closed_days: int = 30) -> int:
    """Delete the rows retention allows; returns the ledger rows deleted."""
    raise NotImplementedError("retention.prune_ledger is not implemented yet")
