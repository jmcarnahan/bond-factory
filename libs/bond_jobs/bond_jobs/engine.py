"""The queue engine: enqueue, claim, run, finish, reclaim.

Times are stored as naive UTC. Every public function accepts aware or naive datetimes and normalises them;
handlers and the ``before`` hook receive naive UTC ``now``. ``now`` is the scheduling clock and ``real_now`` the
wall clock (see ``bond_jobs.clock``): lock stamps and stall checks use ``real_now`` only.
"""

import logging
import os
import socket
import threading
import weakref
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from bond_jobs.clock import Clock, SystemClock, to_naive_utc
from bond_jobs.constants import (
    DEAD,
    DEFAULT_MAX_ATTEMPTS,
    DONE,
    ERROR_MAX_CHARS,
    PENDING,
    RUNNING,
    STALE_AFTER,
    STALLED_MESSAGE,
    backoff,
)
from bond_jobs.loop import Loop, main, start_inline

__all__ = [
    "Clock", "HandlerRegistry", "Loop", "PermanentFailure", "SystemClock", "claim_next", "enqueue", "finish",
    "main", "reclaim_stale", "run_due", "run_job", "start_inline", "tick", "worker_id",
]

LOGGER = logging.getLogger(__name__)

Handler = Callable[[object, dict, datetime], dict]
DeadHook = Callable[[dict], None]


class PermanentFailure(Exception):
    """Raised by a handler when retrying cannot help (a rejected API key): the job goes dead at once."""


def _table(job_table):
    """Accept a Table or a mapped model class."""
    return getattr(job_table, "__table__", job_table)


class HandlerRegistry:
    """Maps job types to handlers ``fn(session, payload, now) -> dict`` and holds dead-job hooks.

    The handler's returned dict may carry ``summary``, ``skipped``, ``reason`` and ``created``; they are read back
    into the result rows of ``run_due``. ``job_table`` is the mapped job model (or its Table) ``tick`` operates on.
    """

    def __init__(self, job_table=None):
        self.job_table = _table(job_table) if job_table is not None else None
        self._handlers: dict[str, Handler] = {}
        self._dead: dict[str, list[DeadHook]] = {}

    def handler(self, job_type: str):
        def register(fn: Handler) -> Handler:
            self._handlers[job_type] = fn
            return fn

        return register

    def get(self, job_type: str) -> Handler | None:
        return self._handlers.get(job_type)

    def on_dead(self, job_type: str):
        """Register ``hook(job_dict_with_error)`` to run when a job of this type goes dead after a run."""

        def register(fn: DeadHook) -> DeadHook:
            self._dead.setdefault(job_type, []).append(fn)
            return fn

        return register

    def dead_hooks(self, job_type: str) -> list[DeadHook]:
        return list(self._dead.get(job_type, []))


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


# -- the queue --------------------------------------------------------------------------------------------------------------


def enqueue(session, job_model, job_type: str, payload: dict, *, run_at: datetime | None = None,
            key: str | None = None, max_attempts: int = DEFAULT_MAX_ATTEMPTS, job_id: str | None = None,
            company_id: str | None = None, now: datetime):
    """Add a job; returns the row, or None when ``key`` already exists (checked first, then guarded by the unique index)."""
    now = to_naive_utc(now)
    table = _table(job_model)
    if key is not None and session.execute(
            select(table.c.id).where(table.c.idempotency_key == key)).first() is not None:
        return None
    fields = {"job_type": job_type, "payload": payload, "run_at": to_naive_utc(run_at or now), "status": PENDING,
              "attempts": 0, "max_attempts": max_attempts, "idempotency_key": key, "created_at": now,
              "updated_at": now}
    if job_id is not None:
        fields["id"] = job_id
    if company_id is not None:
        fields["company_id"] = company_id  # only models built with TenantJobsMixin have the column
    row = job_model(**fields)
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        return None  # another process added the same key between the check and the insert
    return row


def _columns(table):
    c = table.c
    return (c.id, c.job_type, c.payload, c.attempts, c.max_attempts, c.idempotency_key)


def postgres_pick(table, now: datetime):
    """The Postgres claim query: the oldest due pending job, locked so two workers never take the same one."""
    return (select(*_columns(table)).where(table.c.status == PENDING, table.c.run_at <= now)
            .order_by(table.c.run_at, table.c.id).limit(1).with_for_update(skip_locked=True))


def claim_next(engine, job_table, wid: str, *, now: datetime, real_now: datetime) -> dict | None:
    """Atomically take the oldest due pending job: marks it running and counts the attempt. ``locked_at`` is ``real_now``."""
    table, now, real_now = _table(job_table), to_naive_utc(now), to_naive_utc(real_now)
    claimed = {"status": RUNNING, "locked_at": real_now, "locked_by": wid, "attempts": table.c.attempts + 1,
               "updated_at": now}
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            row = conn.execute(postgres_pick(table, now)).first()
            if row is None:
                return None
            conn.execute(update(table).where(table.c.id == row.id).values(**claimed))
            attempts = row.attempts + 1
        else:
            oldest = (select(table.c.id).where(table.c.status == PENDING, table.c.run_at <= now)
                      .order_by(table.c.run_at, table.c.id).limit(1).scalar_subquery())
            row = conn.execute(update(table).where(table.c.id == oldest, table.c.status == PENDING)
                               .values(**claimed).returning(*_columns(table))).first()
            if row is None:
                return None
            attempts = row.attempts
    return {"id": row.id, "job_type": row.job_type, "payload": row.payload or {}, "attempts": attempts,
            "max_attempts": row.max_attempts, "key": row.idempotency_key, "worker": wid}


def finish(engine, job_table, job: dict, *, error: str | None, now: datetime, permanent: bool = False) -> str:
    """Record the outcome: ``done``, ``pending`` (retry after backoff), ``dead``, or ``lost``.

    Only the worker that holds the claim may finish: a job reclaimed after a stall belongs to whoever took it next.
    """
    table, now = _table(job_table), to_naive_utc(now)
    cleared = {"locked_at": None, "locked_by": None}
    if error is None:
        status, values = DONE, {"status": DONE, "last_error": None, **cleared}
    elif permanent or job["attempts"] >= job["max_attempts"]:
        status, values = DEAD, {"status": DEAD, "last_error": error[:ERROR_MAX_CHARS], **cleared}
    else:
        status = PENDING
        values = {"status": PENDING, "last_error": error[:ERROR_MAX_CHARS], **cleared,
                  "run_at": now + backoff(job["attempts"])}
    with engine.begin() as conn:
        changed = conn.execute(
            update(table).where(table.c.id == job["id"], table.c.status == RUNNING,
                                table.c.locked_by == job.get("worker")).values(updated_at=now, **values)).rowcount
    return status if changed else "lost"


def reclaim_stale(engine, job_table, *, now: datetime, real_now: datetime) -> int:
    """Put back jobs that stayed ``running`` over ten REAL minutes (their worker died); returns how many.

    The stalled try counts as an attempt: a job already at ``max_attempts`` goes dead ("Stopped responding").
    """
    table, now, real_now = _table(job_table), to_naive_utc(now), to_naive_utc(real_now)
    cutoff = real_now - STALE_AFTER
    stalled = (table.c.status == RUNNING, table.c.locked_at < cutoff)
    cleared = {"last_error": STALLED_MESSAGE, "locked_at": None, "locked_by": None, "updated_at": now}
    with engine.begin() as conn:
        doomed = conn.execute(select(table.c.id, table.c.job_type, table.c.idempotency_key).where(
            *stalled, table.c.attempts >= table.c.max_attempts)).all()
        dead = conn.execute(update(table).where(*stalled, table.c.attempts >= table.c.max_attempts)
                            .values(status=DEAD, **cleared)).rowcount
        for row in doomed:
            LOGGER.error("job %s (%s, key %s) stopped responding and is dead", row.id, row.job_type,
                         row.idempotency_key)
        back = conn.execute(update(table).where(*stalled).values(status=PENDING, run_at=now, **cleared)).rowcount
    return (dead or 0) + (back or 0)


# -- running ----------------------------------------------------------------------------------------------------------------


def run_job(session_factory, registry: HandlerRegistry, job: dict, now: datetime) -> dict:
    """Run one claimed job in its own session. Raises whatever the handler raises (the caller records it)."""
    fn = registry.get(job["job_type"])
    if fn is None:
        raise RuntimeError(f"No handler for job type {job['job_type']}")
    with session_factory() as session:
        result = fn(session, job["payload"], to_naive_utc(now)) or {}
        session.commit()
    return result


def _fire_dead_hooks(registry: HandlerRegistry, job: dict) -> None:
    for hook in registry.dead_hooks(job["job_type"]):
        try:
            hook(job)
        except Exception:
            LOGGER.warning("dead-job hook failed for job %s", job["id"], exc_info=True)


def run_due(engine, session_factory, registry: HandlerRegistry, *, clock: Clock, wid: str | None = None,
            limit: int = 200, job_table=None) -> list[dict]:
    """Claim and run every job due now (at most ``limit``); returns one result dict per job.

    ``clock.now()`` is read once per pass (what is due, when retries run). ``clock.real_now()`` is read at EVERY
    claim, so ``locked_at`` is the claim time: a job claimed late in a long pass never looks stale to another
    worker's ``reclaim_stale``."""
    table = _table(job_table) if job_table is not None else registry.job_table
    if table is None:
        raise ValueError("pass job_table or build the registry with HandlerRegistry(job_model)")
    now = to_naive_utc(clock.now())
    wid = wid or worker_id()
    ran: list[dict] = []
    for _ in range(limit):
        job = claim_next(engine, table, wid, now=now, real_now=clock.real_now())
        if job is None:
            break
        error, result, permanent = None, {}, False
        try:
            result = run_job(session_factory, registry, job, now)
        except PermanentFailure as exc:
            LOGGER.warning("job %s (%s) failed for good on attempt %s: %s", job["id"], job["job_type"],
                           job["attempts"], exc, exc_info=True)
            error, permanent = f"{type(exc).__name__}: {exc}", True
        except Exception as exc:
            LOGGER.warning("job %s (%s) failed on attempt %s: %s", job["id"], job["job_type"], job["attempts"],
                           exc, exc_info=True)
            error = f"{type(exc).__name__}: {exc}"
        status = finish(engine, table, job, error=error, now=now, permanent=permanent)
        if status == DEAD:
            LOGGER.error("job %s (%s, key %s) is dead after %s attempts: %s", job["id"], job["job_type"],
                         job["key"], job["attempts"], error)
            _fire_dead_hooks(registry, {**job, "error": error})
        skipped = bool(result.get("skipped"))
        ran.append({"id": job["id"], "job_type": job["job_type"], "key": job["key"], "status": status,
                    "error": error, "summary": result.get("summary"), "skipped": skipped,
                    "reason": (result.get("reason") or "nothing_due") if skipped else None,
                    "created": result.get("created", [])})
    return ran


_BEFORE_LAST: "weakref.WeakKeyDictionary[HandlerRegistry, datetime]" = weakref.WeakKeyDictionary()


def _before_due(registry: HandlerRegistry, clock: Clock, every: float | None) -> bool:
    """True when the throttled ``before`` hook should run now. The wall clock times it."""
    if every is None:
        return True
    last = _BEFORE_LAST.get(registry)
    return last is None or (to_naive_utc(clock.real_now()) - last).total_seconds() >= every


def tick(engine, session_factory, registry: HandlerRegistry, clock: Clock, *, before=None,
         before_every: float | None = None, limit: int = 200, job_table=None) -> list[dict]:
    """One pass: reclaim stale jobs, run ``before(session, now)`` (the app's scheduler), run what is due.

    A failing ``before`` hook is logged and the due jobs still run. With ``before_every`` (seconds) the hook runs
    at most that often per process (the first tick always runs it; a hook that fails runs again on the next tick);
    ``None`` runs it on every tick.
    """
    table = _table(job_table) if job_table is not None else registry.job_table
    if table is None:
        raise ValueError("pass job_table or build the registry with HandlerRegistry(job_model)")
    now = clock.now()
    reclaim_stale(engine, table, now=now, real_now=clock.real_now())
    if before is not None and _before_due(registry, clock, before_every):
        try:
            with session_factory() as session:
                before(session, to_naive_utc(now))
                session.commit()
            if before_every is not None:
                _BEFORE_LAST[registry] = to_naive_utc(clock.real_now())  # only a successful run starts the wait
        except Exception:
            LOGGER.warning("before-tick hook failed", exc_info=True)
    return run_due(engine, session_factory, registry, clock=clock, limit=limit, job_table=table)
