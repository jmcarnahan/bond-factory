"""Housekeeping on the job table: cancel pending jobs by key, prune finished ones."""

from datetime import datetime

from sqlalchemy import delete, select

from bond_jobs.clock import to_naive_utc
from bond_jobs.constants import DEAD, DONE, PENDING

CHUNK = 500  # ids per DELETE statement (older SQLite builds cap bind parameters)


def _table(job_table):
    """Accept a Table or a mapped model class."""
    return getattr(job_table, "__table__", job_table)


def cancel(engine, *, idempotency_key: str, job_table) -> int:
    """Delete the pending jobs with this idempotency key; returns the count. A running job is left alone."""
    table = _table(job_table)
    with engine.begin() as conn:
        result = conn.execute(delete(table).where(table.c.idempotency_key == idempotency_key,
                                                  table.c.status == PENDING))
    return result.rowcount or 0


def prune(engine, *, older_than: datetime, statuses=(DONE, DEAD), job_table, limit: int = 10000) -> int:
    """Delete finished jobs last updated before ``older_than`` (at most ``limit``); returns the count.

    Only ``done`` and ``dead`` rows can go: ``pending`` and ``running`` in ``statuses`` are ignored.
    """
    table = _table(job_table)
    wanted = [s for s in statuses if s in (DONE, DEAD)]
    if not wanted:
        return 0
    cutoff = to_naive_utc(older_than)
    with engine.begin() as conn:
        ids = conn.execute(select(table.c.id).where(table.c.status.in_(wanted), table.c.updated_at < cutoff)
                           .order_by(table.c.updated_at).limit(limit)).scalars().all()
        deleted = 0
        for i in range(0, len(ids), CHUNK):
            result = conn.execute(delete(table).where(table.c.id.in_(ids[i:i + CHUNK]),
                                                      table.c.status.in_(wanted)))
            deleted += result.rowcount or 0
    return deleted
