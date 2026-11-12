"""Run plain functions on a timer. No jobs table, no SQLAlchemy.

``run_schedule`` is one thread that runs the earliest-due entry next. The rate is fixed: an entry's next due
time is its previous due time plus ``seconds``, not the time it finished, so a slow run does not drift the
schedule. If a run (or a busy neighbour) made it miss one or more periods, it runs once and realigns to the
next point on its grid; there is no burst of catch-up runs.
"""

import argparse
import logging
import math
import random
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

LOGGER = logging.getLogger(__name__)

MIN_SECONDS = 0.01  # a smaller period is almost certainly a bug (milliseconds passed as seconds)


@dataclass(frozen=True)
class Every:
    """Run ``fn`` every ``seconds``. ``jitter`` delays each run by a random 0..jitter seconds (the grid itself
    does not move, so jitter never accumulates). ``run_first=False`` waits one period before the first run."""

    seconds: float
    fn: Callable[[], Any]
    name: str = ""
    jitter: float = 0.0
    run_first: bool = True

    def __post_init__(self) -> None:
        if not math.isfinite(self.seconds) or self.seconds < MIN_SECONDS:
            raise ValueError(f"seconds must be a finite number of at least {MIN_SECONDS}, got {self.seconds}")
        if not math.isfinite(self.jitter) or self.jitter < 0:
            raise ValueError(f"jitter must be a finite number, not negative, got {self.jitter}")
        if not self.name:
            object.__setattr__(self, "name", getattr(self.fn, "__name__", "job"))


Guard = Callable[[Every], bool]
OnResult = Callable[[Every, Any, "BaseException | None"], None]


class _Slot:
    def __init__(self, entry: Every, now: float):
        self.entry = entry
        self.grid = now if entry.run_first else now + entry.seconds
        self.at = self._jittered()

    def _jittered(self) -> float:
        extra = random.uniform(0.0, self.entry.jitter) if self.entry.jitter else 0.0
        return self.grid + extra

    def advance(self, now: float) -> None:
        self.grid += self.entry.seconds
        if self.grid <= now:  # missed one or more periods: realign to the next grid point, no burst
            self.grid += self.entry.seconds * (int((now - self.grid) // self.entry.seconds) + 1)
        self.at = self._jittered()


def _run_one(entry: Every, on_result: OnResult | None) -> BaseException | None:
    """Run one entry; return its error (None on success). ``SystemExit`` and ``KeyboardInterrupt`` are not caught."""
    result: Any = None
    error: BaseException | None = None
    try:
        result = entry.fn()
    except Exception as exc:
        error = exc
        LOGGER.exception("%s failed", entry.name)
    if on_result is not None:
        try:
            on_result(entry, result, error)
        except Exception:
            LOGGER.exception("%s on_result failed", entry.name)
    return error


def _allowed(entry: Every, guard: Guard | None) -> bool:
    if guard is None:
        return True
    try:
        return bool(guard(entry))
    except Exception:
        LOGGER.exception("%s guard failed; run skipped", entry.name)
        return False


def run_schedule(
    entries: Sequence[Every],
    *,
    stop: threading.Event | None = None,
    install_signals: bool = True,
    on_result: OnResult | None = None,
    guard: Guard | None = None,
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], Any] | None = None,
) -> None:
    """Run ``entries`` until ``stop`` is set (SIGINT/SIGTERM set it when ``install_signals``; the previous
    handlers are restored on exit). A raising entry is logged and the others carry on. ``guard(entry)`` returning
    False skips that run (a cross-process lock belongs there; the lib ships none). ``on_result(entry, result,
    error)`` sees every run, ``error`` is None on success. ``clock`` and ``wait`` are injectable for tests; ``wait``
    must block for the delay it is given (one that returns at once spins the loop).

    ``guard`` is asked before each run and has no release hook, so it suits a lock held for the process lifetime (for
    example a session-level advisory lock taken once), not a lock taken and dropped around each run.

    The first SIGINT/SIGTERM sets ``stop`` and puts the previous handlers back at once, so a second signal interrupts
    a job that does not return. ``SystemExit`` or ``KeyboardInterrupt`` raised by an entry ends the schedule: it
    propagates after the handlers are restored and ``on_result`` is not called for it."""
    if not entries:
        raise ValueError("run_schedule needs at least one entry")
    stop = stop if stop is not None else threading.Event()
    wait = wait if wait is not None else stop.wait
    # wait() rejects a timeout above threading.TIMEOUT_MAX; a longer delay is waited in capped pieces
    previous: dict[int, Any] = {}

    def restore() -> None:
        while previous:
            sig, handler = previous.popitem()
            if handler is not None:  # a handler installed outside Python reads back as None: nothing to restore
                signal.signal(sig, handler)

    def on_signal(*_: Any) -> None:
        stop.set()
        restore()  # a second signal now takes the previous behaviour

    if install_signals and threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, on_signal)
    try:
        start = clock()
        slots = [_Slot(entry, start) for entry in entries]
        while not stop.is_set():
            slot = min(slots, key=lambda s: s.at)
            delay = slot.at - clock()
            if delay > 0:
                wait(min(delay, threading.TIMEOUT_MAX))
                if stop.is_set():
                    break
                if slot.at - clock() > 0:  # woke early (an injected wait may): look again
                    continue
            if _allowed(slot.entry, guard):
                _run_one(slot.entry, on_result)
            slot.advance(clock())
    finally:
        restore()


def run_every(fn: Callable[[], Any], seconds: float, **kw: Any) -> None:
    """One function on one timer. Extra keywords go to ``Every`` (name, jitter, run_first) or ``run_schedule``."""
    entry_keys = {"name", "jitter", "run_first"}
    entry = Every(seconds, fn, **{k: kw.pop(k) for k in list(kw) if k in entry_keys})
    run_schedule([entry], **kw)


def run_cli(argv: Sequence[str] | None, entries: Sequence[Every], *, guard: Guard | None = None,
            on_result: OnResult | None = None, stop: threading.Event | None = None,
            install_signals: bool = True) -> int:
    """Worker entry point. ``--once`` runs each entry once and exits 0 if all succeeded, 1 if any raised.
    ``--watch`` (the default) runs the schedule until SIGINT/SIGTERM; ``--interval N`` (finite, at least ``MIN_SECONDS``)
    sets every entry's period; ``--once`` ignores it. ``guard``, ``on_result``, ``stop`` and ``install_signals`` go to
    ``run_schedule``. ``--once`` also honours ``guard`` (a skipped entry is not a failure) and calls ``on_result``.
    ``guard`` is asked before each run and has no release hook: use a lock held for the process lifetime."""
    parser = argparse.ArgumentParser(description="Run the scheduled functions.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="run each entry once, then exit (1 if any raised)")
    mode.add_argument("--watch", action="store_true", help="run on the schedule until stopped (the default)")
    parser.add_argument("--interval", type=float, help="seconds between runs; replaces every entry's period")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    if args.interval is not None and (not math.isfinite(args.interval) or args.interval < MIN_SECONDS):
        parser.print_usage(sys.stderr)
        print(f"error: --interval must be a finite number of at least {MIN_SECONDS}", file=sys.stderr)
        return 2
    if args.once:
        failed = False
        for entry in entries:
            if _allowed(entry, guard) and _run_one(entry, on_result) is not None:
                failed = True
        return 1 if failed else 0
    use = [replace(e, seconds=args.interval) for e in entries] if args.interval is not None else list(entries)
    run_schedule(use, stop=stop, install_signals=install_signals, on_result=on_result, guard=guard)
    return 0
