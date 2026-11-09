"""The two clocks the queue uses.

``now()`` is the scheduling clock: it decides what is due and when a retry runs. An app may offset it
(a demo that pretends to be another day). ``real_now()`` is the wall clock: lock stamps and stall checks use
it, so a job that has run ten real seconds is never stale just because the scheduling clock is shifted.
Both return aware UTC datetimes; the table stores naive UTC.
"""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def real_now(self) -> datetime: ...


class SystemClock:
    """Both clocks are the wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def real_now(self) -> datetime:
        return datetime.now(UTC)


def to_naive_utc(value: datetime) -> datetime:
    """Aware datetimes convert to UTC and lose the tzinfo; naive ones are taken as UTC already."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
