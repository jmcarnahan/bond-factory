"""Database-backed background job queue and worker."""

from bond_jobs.clock import Clock, SystemClock, to_naive_utc
from bond_jobs.constants import (
    BACKOFF_BASE,
    BACKOFF_MAX,
    DEFAULT_MAX_ATTEMPTS,
    POLL_SECONDS,
    STALE_AFTER,
    backoff,
)
from bond_jobs.engine import (
    HandlerRegistry,
    PermanentFailure,
    claim_next,
    enqueue,
    finish,
    reclaim_stale,
    run_due,
    run_job,
    tick,
    worker_id,
)
from bond_jobs.loop import Loop, main, start_inline
from bond_jobs.maintenance import cancel, prune
from bond_jobs.models import JobsMixin, TenantJobsMixin

__version__ = "0.1.0"

__all__ = [
    "BACKOFF_BASE",
    "BACKOFF_MAX",
    "DEFAULT_MAX_ATTEMPTS",
    "POLL_SECONDS",
    "STALE_AFTER",
    "Clock",
    "HandlerRegistry",
    "JobsMixin",
    "Loop",
    "PermanentFailure",
    "SystemClock",
    "TenantJobsMixin",
    "backoff",
    "cancel",
    "claim_next",
    "enqueue",
    "finish",
    "main",
    "prune",
    "reclaim_stale",
    "run_due",
    "run_job",
    "start_inline",
    "tick",
    "to_naive_utc",
    "worker_id",
]
