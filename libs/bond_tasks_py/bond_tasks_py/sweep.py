"""The sweep: claim the current notice stage of each open dated task, once, across workers."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from bond_tasks_py.compose import default_compose
from bond_tasks_py.dialect import ensure_savepoint_safe
from bond_tasks_py.due import backfill_due_at
from bond_tasks_py.models import TaskStatus
from bond_tasks_py.notify_protocols import STAGES, Compose, Recipients, TransactionalNotifier
from bond_tasks_py.permissions import DefaultPermissions
from bond_tasks_py.protocols import Permissions, Preferences, UserPrefs
from bond_tasks_py.quiet import sendable
from bond_tasks_py.stages import (
    MAX_LEAD_MINUTES,
    StageTime,
    current_stage,
    deadline_token,
    effective_zone,
    notice_id,
    stage_times,
)
from bond_tasks_py.sweep_claim import claim_rows, existing_ids, payload_of, table_of
from bond_tasks_py.timeutil import to_naive_utc


@dataclass(frozen=True)
class SweepResult:
    claimed: int = 0
    skipped: int = 0
    queued: int = 0
    repaired: int = 0
    errors: int = 0  # rows whose notifier failed even alone: nothing was written, the next sweep retries them


def default_recipients(task: Any, stage: str) -> list[str]:
    """close and due go to the responsible user (the assignee, else the owner); past goes to the responsible user
    and the owner (once when they are the same person)."""
    responsible = task.assigned_user_id or task.owner_user_id
    if stage == "past" and task.owner_user_id != responsible:
        return [responsible, task.owner_user_id]
    return [responsible]


def notice_recipients(task: Any) -> set[str]:
    """Every user who can hold a notice for the task: the owner and the assignee. A host that reassigns compares
    this set before and after and puts away the notices of the users who left."""
    return {user for user in (task.owner_user_id, task.assigned_user_id) if user}


def _actions(task: Any, user_id: str, permissions: Permissions) -> tuple[str, ...]:
    actions = ["done"] if permissions.can_complete(task, user_id) else []
    actions.append("snooze")
    if permissions.can_own(task, user_id):
        actions.append("cancel")
    return tuple(actions)


@dataclass(frozen=True)
class _Pending:
    """A notice the sweep could claim now; not composed yet (composing waits until the ledger says it is new)."""

    id: str
    task: Any
    user: str
    prefs: UserPrefs
    stage: StageTime
    token: str


def _pending_for_task(session: Any, task: Any, *, now: datetime, tz: str, max_past: int,
                      recipients: Recipients | None, prefs_of: Any) -> list[_Pending]:
    asked: dict[str, list[str]] = {}

    def users_of(stage_name: str) -> list[str]:  # asked at most once per stage, and only for current stages
        if stage_name not in asked:
            asked[stage_name] = (default_recipients(task, stage_name) if recipients is None
                                 else list(recipients.for_stage(session, task, stage_name)))
        return asked[stage_name]

    def current_of(user: str) -> StageTime | None:
        return current_stage(task, prefs_of(user), tz, now, max_past=max_past)

    responsible = task.assigned_user_id or task.owner_user_id
    candidates: set[str] = set()
    for seed in {responsible, task.owner_user_id}:
        seed_stage = current_of(seed)
        if seed_stage is not None:
            candidates.update(users_of(seed_stage.stage))
    token = deadline_token(task)
    found = []
    for user in sorted(candidates):
        prefs: UserPrefs = prefs_of(user)
        stage = current_of(user)
        if stage is None or user not in users_of(stage.stage):
            continue
        if not sendable(task, stage.stage, prefs, effective_zone(prefs, tz), now):
            continue
        found.append(_Pending(notice_id(task.id, user, stage.stage, stage.seq, token), task, user, prefs, stage,
                              token))
    return found


def _grandfather_rows(session: Any, task: Any, *, now: datetime, tz: str, max_past: int,
                      recipients: Recipients | None, prefs_of: Any) -> list[dict]:
    """A skipped ledger row for every stage (close, due, past up to ``max_past``) of every user who could be sent
    one, so no later pass claims any of them."""
    users: set[str] = set()
    for stage_name in STAGES:
        users.update(default_recipients(task, stage_name) if recipients is None
                     else recipients.for_stage(session, task, stage_name))
    token = deadline_token(task)
    rows = []
    for user in sorted(users):
        for stage in stage_times(task, prefs_of(user), tz, now, max_past=max_past, past_days=36500):
            payload = payload_of(title=task.title, body="", due_at=task.due_at, priority=task.priority,
                                 route=f"/tasks/{task.id}", actions=(), last=stage.last)
            rows.append({"id": notice_id(task.id, user, stage.stage, stage.seq, token), "task_id": task.id,
                         "user_id": user, "stage": stage.stage, "seq": stage.seq, "deadline_token": token,
                         "status": "skipped", "stage_at": stage.at, "payload": payload, "claimed_at": now})
    return rows


def _row_of(item: _Pending, *, now: datetime, since: datetime | None, compose: Compose | None,
            permissions: Permissions) -> dict:
    task, stage = item.task, item.stage
    if compose is None:
        title, body = default_compose(task, stage.stage, stage.seq, item.prefs, last=stage.last)
    else:
        title, body = compose(task, stage.stage, stage.seq, item.prefs)
    payload = payload_of(title=title, body=body, due_at=task.due_at, priority=task.priority,
                         route=f"/tasks/{task.id}", actions=_actions(task, item.user, permissions), last=stage.last)
    skipped = since is not None and stage.at < since
    return {"id": item.id, "task_id": task.id, "user_id": item.user, "stage": stage.stage, "seq": stage.seq,
            "deadline_token": item.token, "status": "skipped" if skipped else "claimed", "stage_at": stage.at,
            "payload": payload, "claimed_at": now}


def sweep_due(session: Any, *, task_model: Any, ledger_model: Any, outbox_model: Any = None, now: datetime,
              prefs: Preferences, tz: str = "UTC", transactional: Sequence[TransactionalNotifier] = (),
              channels: Sequence[str] = (), recipients: Recipients | None = None, compose: Compose | None = None,
              permissions: Permissions | None = None, since: datetime | None = None, max_past: int = 5,
              limit: int = 500, grandfather_before: datetime | None = None) -> SweepResult:
    """Claim and queue the current stage per (task, recipient). Flushes, never commits.

    ``Preferences.for_user`` is called once per user within one call. When a claim batch fails because a
    transactional notifier raises, the batch is retried row by row in per-row savepoints, and a row that still
    fails writes nothing (it is logged with its notice id and counted in ``errors``), so a transient failure
    loses no notice: the next sweep retries it while its stage is current, and one bad row never blocks the
    others. Ledger statuses: "claimed" and "skipped" (before ``since``).

    ``grandfather_before`` is for switching the sweep on over old data: a task whose ``due_at`` is before it gets a
    "skipped" ledger row for EVERY stage (close, due, and the past series up to ``max_past``), so no later pass
    claims it and no notice tail follows. A task due at or after it is untouched. Rows with a NULL ``due_at`` are
    invisible to the sweep, and the built-in ``backfill_due_at`` fills at most ``limit`` rows per call, so a large
    adopter backfills to completion first and only then passes the activation time here.

    Recipients are asked only for the stage that is current for the responsible user or the owner. An idle
    sweep (everything already claimed) issues no INSERT and composes nothing: the ledger is asked which notice
    ids exist before titles and bodies are built, and only the missing ones are composed and inserted.
    Needs SQLite 3.35 or later (INSERT ... RETURNING); claim statements stay under 900 bind parameters.

    On SQLite with the default driver settings a released savepoint commits the outer transaction, so
    "flushes, never commits" holds only with the SQLAlchemy-documented setup (``isolation_level=None`` plus a
    BEGIN event). The sweep therefore raises RuntimeError on an engine not prepared by
    ``dialect.sqlite_savepoint_setup(engine)`` (call it before the first connection). PostgreSQL is unaffected.

    Tasks are read in pages of ``limit`` in task id order (rows are claimed in task id, user id order, so
    concurrent workers never lock in opposite orders); every candidate is visited in one call. ``channels`` are
    outbox channel names and need ``outbox_model``."""
    if channels and outbox_model is None:
        raise ValueError("channels need an outbox_model")
    ensure_savepoint_safe(session)
    now = to_naive_utc(now)
    since = to_naive_utc(since) if since is not None else None
    grandfather_before = to_naive_utc(grandfather_before) if grandfather_before is not None else None
    permissions = permissions or DefaultPermissions()
    memo: dict[str, UserPrefs] = {}

    def prefs_of(user_id: str) -> UserPrefs:
        if user_id not in memo:
            memo[user_id] = prefs.for_user(session, user_id)
        return memo[user_id]

    repaired = backfill_due_at(session, task_model=task_model, prefs=prefs, tz=tz, now=now, limit=limit)
    ledger = table_of(ledger_model)
    claimed = skipped = queued = errors = 0
    # a task whose last notice is over (past its mornings, whatever the zone) is no candidate any more
    oldest = now - timedelta(days=max_past + 3)
    last_id = None
    while True:
        query = select(task_model).where(
            task_model.status == TaskStatus.OPEN.value, task_model.due_at.is_not(None),
            task_model.due_at <= now + timedelta(minutes=MAX_LEAD_MINUTES), task_model.due_at >= oldest)
        if last_id is not None:
            query = query.where(task_model.id > last_id)
        tasks = session.execute(query.order_by(task_model.id).limit(limit)).scalars().all()
        if not tasks:
            break
        last_id = tasks[-1].id
        found: list[_Pending] = []
        old_rows: list[dict] = []
        for task in tasks:
            if grandfather_before is not None and task.due_at < grandfather_before:
                old_rows += _grandfather_rows(session, task, now=now, tz=tz, max_past=max_past,
                                              recipients=recipients, prefs_of=prefs_of)
                continue
            found += _pending_for_task(session, task, now=now, tz=tz, max_past=max_past, recipients=recipients,
                                       prefs_of=prefs_of)
        have = existing_ids(session, ledger, [item.id for item in found] + [row["id"] for row in old_rows])
        rows = [_row_of(item, now=now, since=since, compose=compose, permissions=permissions)
                for item in found if item.id not in have]  # compose only what will be inserted
        rows += [row for row in old_rows if row["id"] not in have]
        got = claim_rows(session, ledger, outbox_model, rows, transactional, channels, now)
        claimed, skipped, queued, errors = claimed + got[0], skipped + got[1], queued + got[2], errors + got[3]
        if len(tasks) < limit:
            break
    session.flush()
    return SweepResult(claimed=claimed, skipped=skipped, queued=queued, repaired=repaired, errors=errors)
