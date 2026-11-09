"""Queue tuning constants and the retry backoff curve."""

from datetime import timedelta

POLL_SECONDS = 2.0
STALE_AFTER = timedelta(minutes=10)
BACKOFF_BASE = timedelta(seconds=30)
BACKOFF_MAX = timedelta(minutes=15)
DEFAULT_MAX_ATTEMPTS = 5

# Job statuses stored in ``background_jobs.status``.
PENDING = "pending"
RUNNING = "running"
DONE = "done"
DEAD = "dead"

ERROR_MAX_CHARS = 2000
STALLED_MESSAGE = "Stopped responding"


def backoff(attempts: int) -> timedelta:
    """Delay before the next try after ``attempts`` tries: 30 s doubling, capped at 15 minutes."""
    return min(BACKOFF_BASE * (2 ** min(max(attempts - 1, 0), 30)), BACKOFF_MAX)  # exponent capped: no overflow
