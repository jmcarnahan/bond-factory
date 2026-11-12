"""Notice outbox: one row per (ledger row, external channel), inserted in the claim's transaction. The inbox has no
outbox row: its notice is written in the claim itself. Delivery is at-least-once; every channel must be
idempotent on ``notice_id``, or listed in ``at_most_once``."""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, and_, func, or_, select, update
from sqlalchemy.orm import declared_attr

from bond_tasks_py.dialect import ensure_savepoint_safe
from bond_tasks_py.models import TaskStatus
from bond_tasks_py.notify_protocols import Notifier
from bond_tasks_py.stages import deadline_token
from bond_tasks_py.sweep_claim import make_notice, table_of
from bond_tasks_py.timeutil import to_naive_utc

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


UNROUTED_DAYS = 7  # a row for a channel with no notifier waits this long, then fails
KEY_CHUNK = 100  # keys per lease UPDATE (keeps the WHERE clause shallow)


@dataclass(frozen=True)
class DeliverResult:
    leased: int = 0
    sent: int = 0
    retryable: int = 0
    unregistered: int = 0
    failed: int = 0  # permanent verdict, gave up after ``max_attempts``, or no notifier for 7 days
    superseded: int = 0  # the task was done, cancelled, deleted or moved after the claim: not sent
    unrouted: int = 0  # pending rows whose channel has no notifier (left pending, not leased)


def deliver_pending(session: Any, *, ledger_model: Any, outbox_model: Any, notifiers: Mapping[str, Notifier],
                    now: datetime, commit: Callable[[], None], task_model: Any, limit: int = 100,
                    lease_seconds: int = 300, max_attempts: int = 5,
                    at_most_once: Collection[str] = ()) -> DeliverResult:
    """Send the pending outbox rows, at least once.

    Pending means ``delivered_at IS NULL AND failed_at IS NULL AND (lease_until IS NULL OR lease_until < now)``.
    The rows are leased in one transaction: select the keys of at most ``limit`` pending rows (skipping rows other
    workers hold, on PostgreSQL), then UPDATE exactly those keys with the pending test repeated, so each row is
    leased once. ``commit()`` is called straight after the lease: it must be committed before any send, so other
    workers see it. Then, row by row: send (in a savepoint), stamp, ``commit()``; a crash loses at most the one
    row in flight. A notifier returns "ok" (stamp ``delivered_at``), "retryable" (keep the row for a later
    lease; after ``max_attempts`` it counts as failed), "unregistered" (stamp ``failed_at``: the target is gone)
    or "failed" (permanent: stamp ``failed_at`` at once). A crash between a send and its stamp sends again after
    the lease ends, so every channel must be idempotent on ``notice_id``. ``Notice.attempt`` is the row's lease
    count: 1 on the first send, 2 after one expired lease, so a channel with no idempotency key can look for a
    duplicate only when ``attempt > 1``. A channel named in ``at_most_once`` gets ``delivered_at`` stamped and
    committed BEFORE the send: a crash loses that notice instead of repeating it. When the send then fails or
    raises ("retryable" counts as failed, the row is never leased again), the row keeps ``delivered_at`` and also
    gets ``failed_at`` and ``last_error``, so a monitor on ``failed_at`` sees it. A row that fails before the
    stamp (ledger row gone, attempts used up) gets ``failed_at`` like any channel.

    ``task_model`` is required: a row whose task is gone, no longer open, or has a different deadline token than
    the ledger row (it was postponed) is stamped failed with last_error "superseded" and not sent. An app that
    truly wants no check passes ``task_model=None`` explicitly. Rows of a channel
    with no notifier are not leased; they are reported as ``unrouted`` and fail after 7 days. ``now`` may be aware."""
    ensure_savepoint_safe(session)
    now = to_naive_utc(now)
    out, led = table_of(outbox_model), table_of(ledger_model)
    c = out.c
    known = list(notifiers)
    once_channels = set(at_most_once)
    pending = and_(c.delivered_at.is_(None), c.failed_at.is_(None), or_(c.lease_until.is_(None), c.lease_until < now))
    pick = (select(c.ledger_id, c.channel).where(pending, c.channel.in_(known))
            .order_by(c.created_at, c.ledger_id, c.channel).limit(limit))
    if session.get_bind().dialect.name == "postgresql":
        pick = pick.with_for_update(skip_locked=True)
    keys = [tuple(k) for k in session.execute(pick).all()]
    leased: list[Any] = []
    for start in range(0, len(keys), KEY_CHUNK):
        chunk = or_(*[and_(c.ledger_id == ledger_id, c.channel == channel)
                      for ledger_id, channel in keys[start:start + KEY_CHUNK]])
        leased += session.execute(
            update(out).where(chunk, pending)
            .values(lease_until=now + timedelta(seconds=lease_seconds), attempts=c.attempts + 1)
            .returning(c.ledger_id, c.channel, c.attempts)).all()
    stale = session.execute(update(out).where(
        c.delivered_at.is_(None), c.failed_at.is_(None), c.channel.not_in(known),
        c.created_at < now - timedelta(days=UNROUTED_DAYS)).values(failed_at=now, last_error="no notifier"))
    unrouted = session.execute(select(func.count()).select_from(out).where(pending, c.channel.not_in(known))).scalar()
    commit()  # the lease is visible to every worker before anything is sent
    result = {"leased": len(leased), "sent": 0, "retryable": 0, "unregistered": 0, "failed": stale.rowcount or 0,
              "superseded": 0, "unrouted": unrouted or 0}
    if not leased:
        return DeliverResult(**result)

    ledger_rows = {r.id: dict(r._mapping) for r in session.execute(
        select(led).where(led.c.id.in_([row.ledger_id for row in leased]))).all()}
    for row in sorted(leased, key=lambda r: (r.ledger_id, r.channel)):
        ledger_row = ledger_rows.get(row.ledger_id)
        once = row.channel in once_channels

        def stamp_first(row=row) -> None:
            session.execute(update(out).where(c.ledger_id == row.ledger_id, c.channel == row.channel)
                            .values(delivered_at=now))
            commit()

        verdict, error = _send_one(session, notifiers[row.channel], ledger_row, row.attempts, max_attempts,
                                   task_model, stamp_first if once else None)
        if once and verdict == "retryable":
            verdict = "failed"  # the row is not leased again: record it as failed
        if verdict == "ok":
            values, key = {"delivered_at": now, "last_error": None}, "sent"
        elif verdict == "superseded":
            values, key = {"failed_at": now, "last_error": "superseded"}, "superseded"
        elif verdict == "unregistered":
            values, key = {"failed_at": now, "last_error": "unregistered"}, "unregistered"
        elif once and verdict == "failed":
            # delivered_at stays when the stamp ran (no retry); failed_at tells a monitor the send did not succeed
            values, key = {"failed_at": now, "last_error": error or verdict}, "failed"
        elif verdict == "failed" or row.attempts >= max_attempts:
            values, key = {"failed_at": now, "last_error": error or verdict}, "failed"
        else:
            values, key = {"last_error": error or verdict}, "retryable"
        result[key] += 1
        session.execute(update(out).where(c.ledger_id == row.ledger_id, c.channel == row.channel).values(**values))
        commit()  # stamp each row at once: a crash on the next send must not re-send this one
    return DeliverResult(**result)


def _superseded(session: Any, task_model: Any, ledger_row: dict) -> bool:
    tasks = table_of(task_model)
    task = session.execute(select(tasks).where(tasks.c.id == ledger_row["task_id"])).first()
    return (task is None or task.status != TaskStatus.OPEN.value
            or deadline_token(task) != ledger_row["deadline_token"])


def _send_one(session: Any, notifier: Notifier, ledger_row: dict | None, attempts: int, max_attempts: int,
              task_model: Any, before_send: Callable[[], None] | None = None) -> tuple[str, str | None]:
    """The verdict of one send. A missing ledger row (pruned) and a row leased again after its attempts ran out
    (a crash every time) are permanent failures; a row whose task moved on is "superseded". A notifier that
    raises, or says something unknown, is retryable."""
    if ledger_row is None:
        return "failed", "ledger row is gone"
    if attempts > max_attempts:
        return "failed", "gave up after repeated crashes"
    if task_model is not None and _superseded(session, task_model, ledger_row):
        return "superseded", None
    if before_send is not None:
        before_send()
    try:
        with session.begin_nested():
            verdict = notifier.send(session, make_notice(ledger_row, attempts))
    except Exception as exc:  # noqa: BLE001 - any failure of a channel means try again later
        return "retryable", f"{type(exc).__name__}: {exc}"[:500]
    if verdict not in ("ok", "retryable", "unregistered", "failed"):
        return "retryable", f"unknown verdict {verdict!r}"
    return verdict, None
