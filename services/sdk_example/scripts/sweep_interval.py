"""Run the notice sweep on a timer. No jobs table, no web app: this is the whole worker for an app that has none.

    python scripts/sweep_interval.py --every 60            # forever: sweep and deliver every 60 s, prune once an hour
    python scripts/sweep_interval.py --once                # one pass now, then exit (cron, or a test)
    python scripts/sweep_interval.py --once --now 2026-11-08T10:30:00Z   # as of a given instant

The loop is `bond_jobs.run_schedule` with two entries: the sweep every `--every` seconds, and the prune (the ledger,
the outbox and the inbox) every hour. A pass that raises is logged and the next one runs; SIGINT and SIGTERM stop the
loop cleanly. Each sweep claims what is due (`sweep_due`, which commits) and delivers queued pushes (`deliver_pending`,
which commits per row). The database comes from SDK_EXAMPLE_DATABASE_URL like the service; run `make migrate` first.
Pushes go out only when SDK_EXAMPLE_APNS_KEY_FILE, _KEY_ID and _TEAM_ID are set; otherwise the inbox is still filled.
SDK_EXAMPLE_GRANDFATHER_BEFORE (an ISO instant) makes tasks due before it send nothing: set it when switching the sweep
on over old tasks. SDK_EXAMPLE_START_OF_DAY, _END_OF_DAY and _LEAD_MINUTES are the default work day. Two copies running
at once are safe: the ledger claim is exactly-once and delivery leases its rows. It prints one JSON line per pass.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from collections.abc import Callable
from datetime import UTC, datetime

from bond_jobs import Every, run_schedule

from sdk_example import models  # noqa: F401  (attaches every mixin to Base)
from sdk_example.db import make_engine, make_session_factory
from sdk_example.settings import Settings
from sdk_example.sweep_wiring import run_prune, run_sweep
from sdk_example.todo_wiring import apns_sender, stored_prefs

log = logging.getLogger("sweep_interval")
PRUNE_EVERY = 3600.0


def parse_now(value: str) -> datetime:
    at = datetime.fromisoformat(value)  # Python 3.11+ reads a trailing Z
    return (at.replace(tzinfo=UTC) if at.tzinfo is None else at).astimezone(UTC).replace(tzinfo=None)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sweep_pass(factory, settings: Settings, sender, now: datetime) -> dict:
    result = run_sweep(factory, prefs=stored_prefs(settings), tz=settings.tz, sender=sender, now=now,
                       grandfather_before=settings.grandfather_before)
    return {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), **result}


def prune_pass(factory, now: datetime) -> dict:
    return {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "prune": run_prune(factory, now=now)}


def one_pass(factory, settings: Settings, sender, now: datetime) -> dict:
    """What `--once` prints: the sweep and the prune as of `now`, in one record."""
    return {**sweep_pass(factory, settings, sender, now), "prune": prune_pass(factory, now)["prune"]}


def entries(factory, settings: Settings, sender, every: float) -> list[Every]:
    """The two schedules: the sweep every `every` seconds and the prune hourly (each reads the clock when it runs)."""
    return [Every(every, lambda: sweep_pass(factory, settings, sender, utcnow()), name="sweep"),
            Every(PRUNE_EVERY, lambda: prune_pass(factory, utcnow()), name="prune")]


def print_result(entry: Every, result: dict | None, error: BaseException | None) -> None:
    """One JSON line per successful pass (a failed one is already logged by the runner)."""
    if error is None and result is not None:
        print(json.dumps(result), flush=True)


def main(argv: list[str] | None = None, *, run: Callable[..., None] = run_schedule) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--every", type=float, default=60.0, help="seconds between sweeps, at least 1 (default 60)")
    parser.add_argument("--once", action="store_true", help="one pass, then exit (prunes too)")
    parser.add_argument("--now", help="with --once: the instant to sweep as of (ISO 8601; default the real time)")
    args = parser.parse_args(argv)
    if not (math.isfinite(args.every) and args.every >= 1):
        parser.error("--every must be at least 1 second")
    if args.now and not args.once:
        parser.error("--now needs --once")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    factory = make_session_factory(make_engine(settings))
    sender = apns_sender()
    if args.once:
        print(json.dumps(one_pass(factory, settings, sender, parse_now(args.now) if args.now else utcnow())))
        return 0
    run(entries(factory, settings, sender, args.every), on_result=print_result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
