"""Shared test support for the stage, sweep, outbox and retention tests: fakes and fixtures. Loaded by conftest
as a pytest plugin."""
import json
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bond_tasks_py import UserPrefs
from bond_tasks_py.dialect import sqlite_savepoint_setup

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "tasks"


def parse_z(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value.removesuffix("Z"))


def fmt_z(value: datetime | None) -> str | None:
    return None if value is None else value.strftime("%Y-%m-%dT%H:%M:%SZ")


def hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def load_cases() -> list[dict]:
    return json.loads((FIXTURES / "stage_times.json").read_text())


def task_from_json(data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=data["id"], status=data["status"], owner_user_id=data["owner_user_id"],
        assigned_user_id=data["assigned_user_id"],
        due_date=date.fromisoformat(data["due_date"]) if data["due_date"] else None,
        due_time=data["due_time"], due_at=parse_z(data["due_at"]),
        remind_minutes_before=data["remind_minutes_before"], title="Call the plumber", priority=2)


def prefs_from_json(data: dict) -> UserPrefs:
    return UserPrefs(time_zone=data["time_zone"], start_of_day=hhmm(data["start_of_day"]),
                     end_of_day=hhmm(data["end_of_day"]), lead_minutes=data["lead_minutes"])


def sqlite_engine():
    """An in-memory SQLite engine on one shared connection, with the documented savepoint workaround (the
    driver's own transaction handling breaks SAVEPOINT)."""
    from conftest import Base

    engine = sqlite_savepoint_setup(
        create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool))
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def sq_factory():
    return sessionmaker(bind=sqlite_engine(), expire_on_commit=False)


class MapPrefs:
    """``Preferences`` from a dict (user id to prefs, ``default`` for others); counts calls per user."""

    def __init__(self, by_user: dict | None = None, default: UserPrefs | None = None) -> None:
        self.by_user = by_user or {}
        self.default = default or UserPrefs(time_zone="America/Los_Angeles")
        self.calls: dict[str, int] = {}

    def for_user(self, session, user_id):
        self.calls[user_id] = self.calls.get(user_id, 0) + 1
        return self.by_user.get(user_id, self.default)


class FakeInbox:
    """A transactional notifier: records the notices; raises when a batch holds a notice of a bad user."""

    def __init__(self, bad_users=()) -> None:
        self.written: list = []
        self.batches: list[int] = []
        self.bad_users = set(bad_users)

    def write(self, session, notices):
        if any(n.user_id in self.bad_users for n in notices):
            raise RuntimeError("inbox write failed")
        self.batches.append(len(notices))
        self.written.extend(notices)


class FakeChannel:
    """An outbox notifier: answers from a script of verdicts (default "ok") and records every send."""

    def __init__(self, verdicts=None, raises=()) -> None:
        self.sent: list = []
        self.verdicts = list(verdicts or [])
        self.raises = list(raises)

    def send(self, session, notice):
        self.sent.append(notice)
        if self.raises:
            exc = self.raises.pop(0)
            if exc is not None:
                raise exc
        return self.verdicts.pop(0) if self.verdicts else "ok"


# ---- PostgreSQL worker processes (spawned; see test_sweep_pg.py) ----------------------------------------------
PG_META = MetaData()
PROBE_NOTICES = Table("probe_notices", PG_META, Column("notice_id", String), Column("user_id", String))
PROBE_DELIVERIES = Table("probe_deliveries", PG_META, Column("notice_id", String), Column("channel", String))


class ProbeInbox:
    """A transactional notifier writing one probe row per notice (no unique key, so duplicates are visible)."""

    def write(self, session, notices):
        session.execute(PROBE_NOTICES.insert(), [{"notice_id": n.notice_id, "user_id": n.user_id} for n in notices])


class ProbeChannel:
    """An outbox notifier writing one probe row per send (no unique key, so duplicates are visible)."""

    def send(self, session, notice):
        session.execute(PROBE_DELIVERIES.insert(), {"notice_id": notice.notice_id, "channel": "chat"})
        return "ok"


def pg_sweep_worker(url, now, limit, mode, seed, results):
    """One OS process, one connection: sweep and commit. ``mode``: sweep, shuffled (rows claimed in a random
    order), crash_before_commit or crash_after_commit (the process dies with os._exit)."""
    import os
    import random

    from conftest import Ledger, Outbox, Task

    from bond_tasks_py import sweep as sweep_module
    from bond_tasks_py.sweep import sweep_due

    if mode == "shuffled":
        rng, original = random.Random(seed), sweep_module.claim_rows

        def shuffled(session, ledger, outbox, rows, *rest):
            return original(session, ledger, outbox, rng.sample(rows, len(rows)), *rest)

        sweep_module.claim_rows = shuffled
    engine = create_engine(url, pool_size=1, max_overflow=0)
    try:
        with Session(engine) as session:
            result = sweep_due(session, task_model=Task, ledger_model=Ledger, outbox_model=Outbox, now=now,
                               prefs=MapPrefs(), transactional=[ProbeInbox()], channels=["chat"], limit=limit)
            if mode == "crash_before_commit":
                os._exit(9)
            session.commit()
            if mode == "crash_after_commit":
                os._exit(9)
        results.put({"claimed": result.claimed, "error": None})
    except Exception as exc:  # noqa: BLE001 - reported to the parent, which fails the test
        results.put({"claimed": 0, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        engine.dispose()


def pg_deliver_worker(url, now, limit, results):
    """One OS process: deliver pending outbox rows until none is left."""
    from conftest import Ledger, Outbox, Task

    from bond_tasks_py.outbox import deliver_pending

    engine = create_engine(url, pool_size=1, max_overflow=0)
    sent = 0
    try:
        with Session(engine) as session:
            while True:
                result = deliver_pending(session, ledger_model=Ledger, outbox_model=Outbox,
                                         notifiers={"chat": ProbeChannel()}, now=now, commit=session.commit,
                                         limit=limit, task_model=Task)
                sent += result.sent
                if result.leased == 0:
                    break
        results.put({"sent": sent, "error": None})
    except Exception as exc:  # noqa: BLE001
        results.put({"sent": sent, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        engine.dispose()
