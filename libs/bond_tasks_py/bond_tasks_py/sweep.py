"""The sweep: claim the current notice stage of each open dated task, once, across workers."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bond_tasks_py.notify_protocols import Compose, Recipients, TransactionalNotifier
from bond_tasks_py.protocols import Permissions, Preferences


@dataclass(frozen=True)
class SweepResult:
    claimed: int = 0
    skipped: int = 0
    queued: int = 0
    repaired: int = 0


def sweep_due(session: Any, *, task_model: Any, ledger_model: Any, outbox_model: Any = None, now: datetime,
              prefs: Preferences, tz: str = "UTC", transactional: Sequence[TransactionalNotifier] = (),
              channels: Sequence[str] = (), recipients: Recipients | None = None, compose: Compose | None = None,
              permissions: Permissions | None = None, since: datetime | None = None, max_past: int = 5,
              limit: int = 500) -> SweepResult:
    """Claim and queue the current stage per (task, recipient). Flushes, never commits.

    ``Preferences.for_user`` is called once per user within one call. When a claim batch fails because a
    transactional notifier raises, the batch is retried row by row in per-row savepoints, and a row that still
    fails is recorded with ledger status "error", so one bad row cannot block the batch forever. Ledger
    statuses: "claimed", "skipped" (before ``since``), "error"."""
    raise NotImplementedError("sweep.sweep_due is not implemented yet")
