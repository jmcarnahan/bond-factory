"""Stages of a task's notices: the ids and the stage current at an instant.

Rules: docs/decisions/2026-11-11-notify-ledger.md. The same cases run against the Dart side through
``fixtures/tasks/stage_times.json`` and ``notice_ids.json``.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bond_tasks_py.protocols import UserPrefs

FNV_OFFSET = 2166136261
FNV_PRIME = 16777619
MAX_LEAD_MINUTES = 10080  # a larger stored lead is accepted on input and treated as this when it is used


@dataclass(frozen=True)
class StageTime:
    stage: str  # close | due | past
    seq: int
    at: datetime  # naive UTC, when the stage starts
    last: bool = False  # the final past-due notice
    send_at: datetime | None = None  # when a sweep running every minute first claims it; None: never sent


def notice_id(task_id: str, user_id: str, stage: str, seq: int, token: str) -> str:
    """The one id on every delivery path across the ledger, the inbox, push and the local notification: sha256 of the key, first 32 hex characters."""
    return hashlib.sha256(f"{task_id}|{user_id}|{stage}|{seq}|{token}".encode()).hexdigest()[:32]


def fnv1a31(text: str) -> int:
    """FNV-1a 32-bit over the UTF-8 bytes, masked to 31 bits: the local notification id."""
    value = FNV_OFFSET
    for byte in text.encode("utf-8"):
        value = ((value ^ byte) * FNV_PRIME) % 2**32
    return value & 0x7FFFFFFF


def deadline_token(task: Any) -> str:
    """The part of a notice id that changes when the deadline moves: ``due_at`` in epoch minutes for a timed
    task, the ISO ``due_date`` for a date-only task, "" when undated.

    Build the epoch minutes from the naive-UTC ``due_at`` with ``calendar.timegm`` or ``replace(tzinfo=UTC)``,
    never ``datetime.timestamp()`` on a naive value (that reads it as local time). A timed task whose ``due_at``
    is None has token "" and no stages until ``due_at`` is known, the same as an undated task."""
    raise NotImplementedError("stages.deadline_token is not implemented yet")


def current_stage(task: Any, prefs: UserPrefs, tz: str, now: datetime, *, max_past: int = 5) -> StageTime | None:
    """The one stage current for this recipient at ``now``, or None."""
    raise NotImplementedError("stages.current_stage is not implemented yet")


def stage_times(task: Any, prefs: UserPrefs, tz: str, now: datetime, *, max_past: int = 5,
                past_days: int = 7) -> list[StageTime]:
    """Every stage start of the task for the recipient up to ``now`` (for fixtures and Dart parity)."""
    raise NotImplementedError("stages.stage_times is not implemented yet")
