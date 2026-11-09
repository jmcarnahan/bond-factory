"""One source of time for a service, with a test freeze that never touches security timestamps.

``Clock.now()`` is what a person reads or a report uses. ``Clock.real_now()`` is the REAL instant, ignoring both the
freeze and any injected ``source``: use it for stamps that another system checks against the real clock (JWT ``exp``,
session revocation, one-time state expiry).

An app that wants a demo clock passes ``source=`` (a callable returning an aware instant); the kit has no demo mode
of its own.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

TzLike = ZoneInfo | str


def _zone(tz: TzLike) -> ZoneInfo:
    return tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)


def _aware_utc(value: datetime, tz: TzLike = "UTC") -> datetime:
    """Naive values are read as local time in ``tz``; aware values are converted."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_zone(tz)).astimezone(UTC)
    return value.astimezone(UTC)


class Clock:
    """``now()`` / ``today(tz)`` with ``freeze``, ``advance`` and ``unfreeze`` for tests."""

    def __init__(self, source: Callable[[], datetime] | None = None) -> None:
        self._source = source
        self._frozen: datetime | None = None

    @property
    def frozen(self) -> bool:
        return self._frozen is not None

    def real_now(self) -> datetime:
        """The REAL current instant (aware UTC). Never affected by ``freeze`` or ``source``."""
        return datetime.now(UTC)

    def now(self) -> datetime:
        """Current instant, aware UTC: the frozen instant, else ``source()``, else the real one."""
        if self._frozen is not None:
            return self._frozen
        if self._source is not None:
            return _aware_utc(self._source())
        return self.real_now()

    def utcnow_naive(self) -> datetime:
        """``now()`` as a naive UTC datetime, for ``sa.DateTime`` columns that store naive UTC."""
        return self.now().replace(tzinfo=None)

    def local_now(self, tz: TzLike = "UTC") -> datetime:
        return self.now().astimezone(_zone(tz))

    def today(self, tz: TzLike = "UTC") -> date:
        """Today's date in ``tz`` (a zone object or an IANA name)."""
        return self.local_now(tz).date()

    def freeze(self, at: datetime, tz: TzLike = "UTC") -> None:
        """Pin ``now()`` to ``at``. A naive value is read as local time in ``tz``."""
        self._frozen = _aware_utc(at, tz)

    def advance(self, delta: timedelta) -> None:
        """Move ``now()`` forward. A running clock is frozen at ``now() + delta`` first."""
        self._frozen = self.now() + delta

    def unfreeze(self) -> None:
        self._frozen = None


#: The default instance an app uses unless it builds its own.
clock = Clock()
