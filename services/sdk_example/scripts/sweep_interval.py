"""Run the notice sweep on a timer. No jobs table, no web app: this is the whole worker for an app that has none.

    python scripts/sweep_interval.py --every 60            # forever: sweep, deliver, and prune once an hour
    python scripts/sweep_interval.py --once                # one pass now, then exit (cron, or a test)
    python scripts/sweep_interval.py --once --now 2026-11-08T10:30:00Z   # as of a given instant

Each pass opens its own session, claims what is due (`sweep_due`, which commits), delivers queued pushes
(`deliver_pending`, which commits per row) and, once an hour, prunes the ledger, the outbox and the inbox. The
database comes from SDK_EXAMPLE_DATABASE_URL like the service; run `make migrate` first. Pushes go out only when
SDK_EXAMPLE_APNS_KEY_FILE, _KEY_ID and _TEAM_ID are set; otherwise the inbox is still filled. Two copies running at once
are safe: the ledger claim is exactly-once and delivery leases its rows. It prints one JSON line per pass.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime

from bond_tasks_py import StoredPreferences

from sdk_example import models  # noqa: F401  (attaches every mixin to Base)
from sdk_example.db import make_engine, make_session_factory
from sdk_example.models.task_settings import TaskUserSettings
from sdk_example.settings import Settings
from sdk_example.sweep_wiring import run_prune, run_sweep
from sdk_example.todo_wiring import apns_sender

log = logging.getLogger("sweep_interval")
PRUNE_EVERY = 3600.0


def parse_now(value: str) -> datetime:
    at = datetime.fromisoformat(value)  # Python 3.11+ reads a trailing Z
    return (at.replace(tzinfo=UTC) if at.tzinfo is None else at).astimezone(UTC).replace(tzinfo=None)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def one_pass(factory, settings: Settings, sender, now: datetime, *, prune: bool) -> dict:
    result = run_sweep(factory, prefs=StoredPreferences(TaskUserSettings), tz=settings.tz, sender=sender, now=now)
    if prune:
        result["prune"] = run_prune(factory, now=now)
    return {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), **result}


def prune_due(last_prune: float | None, now: float) -> bool:
    """The first pass prunes; after that once an hour (monotonic seconds)."""
    return last_prune is None or now - last_prune >= PRUNE_EVERY


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--every", type=float, default=60.0, help="seconds between passes, at least 1 (default 60)")
    parser.add_argument("--once", action="store_true", help="one pass, then exit (prunes too)")
    parser.add_argument("--now", help="with --once: the instant to sweep as of (ISO 8601; default the real time)")
    args = parser.parse_args(argv)
    if args.every < 1:
        parser.error("--every must be at least 1 second")
    if args.now and not args.once:
        parser.error("--now needs --once")
    settings = Settings.from_env()
    factory = make_session_factory(make_engine(settings))
    sender = apns_sender()
    if args.once:
        print(json.dumps(one_pass(factory, settings, sender, parse_now(args.now) if args.now else utcnow(),
                                  prune=True)))
        return 0
    last_prune: float | None = None
    try:
        while True:
            started = time.monotonic()
            prune = prune_due(last_prune, started)
            try:
                print(json.dumps(one_pass(factory, settings, sender, utcnow(), prune=prune)), flush=True)
                last_prune = started if prune else last_prune
            except Exception:
                log.exception("sweep pass failed")
            time.sleep(max(0.0, args.every - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
