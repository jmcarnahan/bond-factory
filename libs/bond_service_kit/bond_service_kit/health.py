"""``GET /health``: named checks run on their own worker threads, so it still answers when the route threads are busy."""

import threading
from collections.abc import Callable
from typing import Any

import anyio
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .rate_limit import thread_limiter

Check = Callable[[], "bool | str"]


class HealthBusy(Exception):
    """Every probe slot is taken by checks that have not finished."""


class _Claim:
    """One probe's claim on a slot, released exactly once: by the worker thread when the check ends, or by the request
    when it gave up before the thread ever started."""

    def __init__(self, pool: threading.BoundedSemaphore) -> None:
        self._pool = pool
        self._lock = threading.Lock()
        self._started = self._abandoned = self._released = False

    def _release(self) -> None:
        if not self._released:
            self._released = True
            self._pool.release()

    def run(self, fn: Callable[[], Any]) -> Any:
        with self._lock:
            if self._abandoned:
                raise HealthBusy("abandoned before it started")
            self._started = True
        try:
            return fn()
        finally:
            with self._lock:
                self._release()

    def abandon(self) -> None:
        with self._lock:
            if not self._started:
                self._abandoned = True
                self._release()


class HealthSlot:
    """Bounds in-flight probes (default one). A check that hangs is abandoned by its request (which answers 503) but its
    thread keeps running, so the slot is freed by the thread ending, never by the request giving up. Repeated probes of a
    wedged database therefore cannot pile up threads."""

    def __init__(self, max_in_flight: int = 1) -> None:
        self._max = max_in_flight
        self._pool = threading.BoundedSemaphore(max_in_flight)

    async def run(self, fn: Callable[[], Any], timeout: float) -> Any:
        """Run ``fn`` on a thread. Raises ``HealthBusy`` (no slot) or ``TimeoutError``."""
        if not self._pool.acquire(blocking=False):
            raise HealthBusy("a probe is already running")
        claim = _Claim(self._pool)
        try:
            with anyio.fail_after(timeout):
                # Its own limiter, NOT anyio's default one: sync routes use that pool, and a probe queued behind
                # them would report "timeout" exactly when the service is busiest.
                return await anyio.to_thread.run_sync(
                    claim.run, fn, abandon_on_cancel=True, limiter=thread_limiter("health", self._max))
        except BaseException:
            claim.abandon()
            raise


def _run_checks(checks: dict[str, Check]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, check in checks.items():
        try:
            result = check()
        except Exception:  # noqa: BLE001 - a check may fail in any way; the answer is "error", never a 500
            out[name] = "error"
            continue
        out[name] = "ok" if result is True or result == "ok" else ("fail" if result is False else str(result))
    return out


def health_router(checks: dict[str, Check], *, slot: HealthSlot | None = None, timeout: float = 5.0,
                  degraded_status: int = 503) -> APIRouter:
    """``GET /health`` -> ``{"status": "ok"|"degraded", "checks": {name: "ok"|"fail"|"error"|<message>}}``.

    A check returns True (or ``"ok"``) when healthy, False or a message string when not, and may raise. When any check is
    not ok, or the probe is slow or busy, the status is ``degraded`` with HTTP ``degraded_status`` (503 by default, so a
    deploy probe keeps the old version serving).
    """
    router = APIRouter()
    probe_slot = slot or HealthSlot()

    @router.get("/health", include_in_schema=False)
    async def health() -> JSONResponse:
        try:
            results = await probe_slot.run(lambda: _run_checks(checks), timeout)
        except HealthBusy:
            results = {name: "busy" for name in checks}
        except TimeoutError:
            results = {name: "timeout" for name in checks}
        ok = all(v == "ok" for v in results.values())
        return JSONResponse(status_code=200 if ok else degraded_status,
                            content={"status": "ok" if ok else "degraded", "checks": results})

    return router
