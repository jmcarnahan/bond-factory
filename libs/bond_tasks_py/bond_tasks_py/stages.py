"""Stages of a task's notices: the ids and the stage current at an instant.

Rules: docs/decisions/2026-11-11-notify-ledger.md. The same cases run against the Dart side through
``fixtures/tasks/stage_times.json`` and ``notice_ids.json``.
"""

import calendar
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bond_tasks_py.due import valid_zone
from bond_tasks_py.models import MORNING_OF, NO_REMINDER, USE_DEFAULT_REMINDER, TaskStatus
from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.quiet import next_work_start, sendable
from bond_tasks_py.timeutil import local_to_utc, to_naive_utc

FNV_OFFSET = 2166136261
FNV_PRIME = 16777619
DUE_WINDOW = timedelta(minutes=15)  # the due stage lasts this long
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

    Epoch minutes come from ``calendar.timegm`` on the naive-UTC ``due_at``, never ``datetime.timestamp()`` (that
    reads a naive value as local time). A timed task whose ``due_at`` is None has token "" and no stages until
    ``due_at`` is known, the same as an undated task."""
    if getattr(task, "due_date", None) is None:
        return ""
    if getattr(task, "due_time", None):
        due_at = getattr(task, "due_at", None)
        if due_at is None:
            return ""
        return str(calendar.timegm(to_naive_utc(due_at).utctimetuple()) // 60)
    return task.due_date.isoformat()


def effective_zone(prefs: UserPrefs, tz: str) -> str:
    """The recipient's zone: their stored one when it is a known IANA name, else the app default."""
    return prefs.time_zone if prefs.time_zone and valid_zone(prefs.time_zone) else tz


def _lead(task: Any, prefs: UserPrefs) -> int | None:
    """Close-stage lead in minutes for the numeric settings (N, -3); None for none and for "morning of" (-1)."""
    setting = task.remind_minutes_before
    if setting >= 0:
        lead = min(setting, MAX_LEAD_MINUTES)
    elif setting == USE_DEFAULT_REMINDER:
        lead = min(prefs.lead_minutes, MAX_LEAD_MINUTES)
    else:
        return None
    return lead if lead > 0 else None


class _Plan:
    """The stage geometry of one task for one recipient."""

    def __init__(self, task: Any, prefs: UserPrefs, zone: str, max_past: int) -> None:
        self.prefs, self.zone, self.max_past = prefs, zone, max_past
        self.due_at: datetime = to_naive_utc(task.due_at)
        self.local_due = self.due_at.replace(tzinfo=UTC).astimezone(ZoneInfo(zone)).date()
        self.close_at = self._close_at(task)

    def _close_at(self, task: Any) -> datetime | None:
        setting = task.remind_minutes_before
        if setting == MORNING_OF:
            start = local_to_utc(self.local_due, self.prefs.start_of_day, self.zone)
            return start if start < self.due_at else None
        if setting == NO_REMINDER:
            return None
        lead = _lead(task, self.prefs)
        return None if lead is None else self.due_at - timedelta(minutes=lead)

    def past_at(self, seq: int) -> datetime:
        if seq == 0:
            return self.due_at + DUE_WINDOW
        return local_to_utc(self.local_due + timedelta(days=seq), self.prefs.start_of_day, self.zone)

    def past_seq(self, now: datetime) -> int:
        """The largest k whose start instant ``past_at(k)`` is not after ``now``: decided by instants, so a
        start_of_day inside a daylight-saving gap or overlap flips exactly at the listed time."""
        local = now.replace(tzinfo=UTC).astimezone(ZoneInfo(self.zone))
        seq = max((local.date() - self.local_due).days + 1, 0)
        while seq > 0 and self.past_at(seq) > now:
            seq -= 1
        while self.past_at(seq + 1) <= now:
            seq += 1
        return seq

    def at(self, now: datetime) -> StageTime | None:
        """The stage current at ``now`` (naive UTC), whether or not it may be sent."""
        if now < self.due_at:
            if self.close_at is not None and now >= self.close_at:
                return StageTime("close", 0, self.close_at)
            return None
        if now < self.due_at + DUE_WINDOW:
            return StageTime("due", 0, self.due_at)
        seq = self.past_seq(now)
        if seq > self.max_past:
            return None
        return StageTime("past", seq, self.past_at(seq), last=seq == self.max_past)


def _plan(task: Any, prefs: UserPrefs, tz: str, max_past: int) -> _Plan | None:
    if task.status != TaskStatus.OPEN.value or task.due_date is None or task.due_at is None:
        return None
    return _Plan(task, prefs, effective_zone(prefs, tz), max_past)


def _with_send_at(task: Any, plan: _Plan, stage: StageTime) -> StageTime:
    """``send_at``: the stage start when it may be sent then, else the next start of the work day when the same
    stage and sequence is still current, else None (it is superseded and never sent)."""
    if sendable(task, stage.stage, plan.prefs, plan.zone, stage.at):
        send_at: datetime | None = stage.at
    else:
        later = next_work_start(plan.prefs, plan.zone, stage.at)
        again = plan.at(later)
        send_at = later if again and (again.stage, again.seq) == (stage.stage, stage.seq) else None
    return StageTime(stage.stage, stage.seq, stage.at, stage.last, send_at)


def current_stage(task: Any, prefs: UserPrefs, tz: str, now: datetime, *, max_past: int = 5) -> StageTime | None:
    """The one stage current for this recipient at ``now`` (naive UTC), or None. It is the stage regardless of
    quiet hours: ask ``quiet.sendable`` whether it may go out now. Which recipients get which stage is
    ``sweep.default_recipients``."""
    plan = _plan(task, prefs, tz, max_past)
    stage = plan.at(to_naive_utc(now)) if plan else None
    return _with_send_at(task, plan, stage) if plan and stage else None


def stage_times(task: Any, prefs: UserPrefs, tz: str, now: datetime, *, max_past: int = 5,
                past_days: int = 7) -> list[StageTime]:
    """The stage starts of the task for the responsible user: close (if any), due, then the past series up to
    ``max_past``, each with when a sweep first sends it. Stages that start more than ``past_days`` before ``now``
    are left out (``past_days`` is a window, not a cap on the series). The "past 0" stage is left out when the
    first morning comes at or before ``due_at`` plus 15 minutes: it could never be current."""
    plan = _plan(task, prefs, tz, max_past)
    if plan is None:
        return []
    stages = []
    if plan.close_at is not None:
        stages.append(StageTime("close", 0, plan.close_at))
    stages.append(StageTime("due", 0, plan.due_at))
    first = 0 if plan.past_at(0) < plan.past_at(1) else 1
    stages += [StageTime("past", seq, plan.past_at(seq), last=seq == max_past) for seq in range(first, max_past + 1)]
    oldest = to_naive_utc(now) - timedelta(days=past_days)
    return [_with_send_at(task, plan, stage) for stage in stages if stage.at >= oldest]
