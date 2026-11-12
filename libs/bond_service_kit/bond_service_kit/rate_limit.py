"""In-memory rate limiting (sliding window) and per-event-loop thread limiters.

Single-process only: with several workers each keeps its own counts. Fine for a floor against abuse, not a quota system.
"""

import asyncio
import logging
import math
import re
import threading
from collections import deque
from collections.abc import Callable

import anyio
from fastapi import Request

from .clock import Clock
from .clock import clock as default_clock
from .errors import RateLimited

LOGGER = logging.getLogger(__name__)
_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_GRAMMAR = re.compile(r"^\s*(\d+)\s*/\s*(\d+)?\s*(second|minute|hour|day)s?\s*$", re.IGNORECASE)
_PRUNE_EVERY = 1000


def parse_rate(rate: str) -> tuple[int, float]:
    """``"20/minute"`` -> ``(20, 60.0)``. ``"5/10 minutes"`` is 5 per 10 minutes."""
    match = _GRAMMAR.match(rate or "")
    if not match:
        raise ValueError(f"bad rate {rate!r}: expected like '20/minute' or '5/10 minutes'")
    count, multiple, unit = match.groups()
    if int(count) < 1:
        raise ValueError("rate count must be at least 1")
    if multiple is not None and int(multiple) < 1:
        raise ValueError(f"bad rate {rate!r}: the window multiple must be at least 1")
    return int(count), float(_UNITS[unit.lower()] * int(multiple or 1))


class RateLimiter:
    """At most ``rate`` hits per key inside the window."""

    def __init__(self, rate: str | Callable[[], str], *, clock: Clock | None = None, enabled: bool = True) -> None:
        """``rate`` is a string, or a callable returning one (read on every call, so an app can take its limits
        from the environment per request). A string is checked here. A callable is first called on first use, so an
        app may read settings that load after import. The parsed result is cached by the string, so a stable value
        costs one parse. If a later call returns a bad value the last good rate stays in force and a warning is
        logged; with no good rate yet the error is raised."""
        self._rate_source = rate
        self._parsed: tuple[str, tuple[int, float]] | None = None
        self._override: tuple[int, float] | None = None
        if not callable(rate):
            self._resolve()  # a bad rate fails here, as before
        self.enabled = enabled
        self._clock = clock or default_clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def _resolve(self) -> tuple[str, int, float]:
        source = self._rate_source
        rate = source() if callable(source) else source
        parsed = self._parsed  # one local snapshot: a concurrent call never mixes two rates
        if parsed is None or parsed[0] != rate:
            try:
                parsed = (rate, parse_rate(rate))
            except ValueError:
                if parsed is None:
                    raise
                LOGGER.warning("bad rate %r; keeping %r", rate, parsed[0])
                rate = parsed[0]
            else:
                self._parsed = parsed
                self._override = None
        count, window = self._override or parsed[1]
        return rate, count, window

    @property
    def rate(self) -> str:
        return self._resolve()[0]

    @rate.setter
    def rate(self, value: str) -> None:
        """Replace the rate source with a fixed string (parsed now; a bad value raises and changes nothing)."""
        parse_rate(value)
        self._rate_source = value
        self._override = None

    @property
    def limit(self) -> int:
        return self._resolve()[1]

    @limit.setter
    def limit(self, value: int) -> None:
        """Override the count until ``rate`` is next set."""
        self._override = (int(value), self._resolve()[2])

    @property
    def window(self) -> float:
        return self._resolve()[2]

    @window.setter
    def window(self, value: float) -> None:
        """Override the window (seconds) until ``rate`` is next set."""
        self._override = (self._resolve()[1], float(value))

    def _stamp(self) -> float:
        # real_now, never now(): a frozen or demo clock must not stretch or collapse a security window.
        return self._clock.real_now().timestamp()

    def allow(self, key: str) -> bool:
        """Count a hit for ``key``; False when it is over the limit (the hit is then not counted)."""
        if not self.enabled:
            return True
        _, limit, window = self._resolve()
        now = self._stamp()
        with self._lock:
            self._calls += 1
            if self._calls % _PRUNE_EVERY == 0:
                self._prune(now, window)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def check(self, key: str) -> None:
        """Like ``allow`` but raises ``RateLimited``."""
        if not self.allow(key):
            raise RateLimited(self.rate)

    def retry_after(self, key: str) -> int:
        """Whole seconds until ``key`` may hit again (0 when it may now)."""
        _, limit, window = self._resolve()
        now = self._stamp()
        with self._lock:
            hits = self._hits.get(key)
            if not hits or len(hits) < limit:
                return 0
            return max(0, math.ceil(hits[0] + window - now))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _prune(self, now: float, window: float) -> None:
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= now - window]:
            del self._hits[key]


class LimiterRegistry:
    """Named limiters, so a route refers to ``"login"`` and the app configures the rate once."""

    def __init__(self) -> None:
        self._items: dict[str, RateLimiter] = {}
        self.enabled = True

    def register(self, name: str, rate: str | Callable[[], str], *, clock: Clock | None = None) -> RateLimiter:
        limiter = RateLimiter(rate, clock=clock)
        self._items[name] = limiter
        return limiter

    def get(self, name: str) -> RateLimiter:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"no rate limiter named {name!r}; call limiters.register({name!r}, '10/minute')") from None

    def reset(self) -> None:
        """Forget every hit (tests)."""
        for limiter in self._items.values():
            limiter.reset()

    def clear(self) -> None:
        self._items.clear()


limiters = LimiterRegistry()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit_dependency(name: str, *, rate: str | Callable[[], str] | None = None,
                          key: Callable[[Request], str] = client_ip):
    """A FastAPI dependency: ``Depends(rate_limit_dependency("login", rate="10/minute"))``.

    ``rate`` registers the limiter on first use; without it the name must be registered before the first request.
    """
    if rate is not None and name not in limiters._items:
        limiters.register(name, rate)

    def dependency(request: Request) -> None:
        if not limiters.enabled:
            return
        limiters.get(name).check(f"{name}:{key(request)}")

    return dependency


class ThreadLimiter:
    """A named ``anyio.CapacityLimiter`` per running event loop.

    A limiter belongs to the loop that first uses it, so one is kept per loop. Give work that must not queue behind the
    route threads (session teardown, health checks, long calls) its own, so it cannot take the route threads' tokens.
    """

    def __init__(self) -> None:
        self._items: dict[tuple[asyncio.AbstractEventLoop, str], anyio.CapacityLimiter] = {}

    def get(self, name: str, tokens: int) -> anyio.CapacityLimiter:
        loop = asyncio.get_running_loop()
        for stale in [k for k in self._items if k[0].is_closed()]:
            del self._items[stale]
        return self._items.setdefault((loop, name), anyio.CapacityLimiter(tokens))


_thread_limiters = ThreadLimiter()


def thread_limiter(name: str, tokens: int) -> anyio.CapacityLimiter:
    """The named limiter for the running event loop (created on first use)."""
    return _thread_limiters.get(name, tokens)
