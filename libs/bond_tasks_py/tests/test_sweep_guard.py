"""The SQLite savepoint guard, the candidate window and the lead cap."""
from datetime import date, datetime, time, timedelta

import pytest
from conftest import Base, Ledger, Outbox, Task
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from support_sweep import FakeInbox, MapPrefs
from test_sweep import add_task, sweep

from bond_tasks_py import UserPrefs
from bond_tasks_py.outbox import deliver_pending
from bond_tasks_py.stages import MAX_LEAD_MINUTES, stage_times

NOW = datetime(2026, 3, 12, 16, 30)


def engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def test_a_plain_sqlite_engine_is_refused_and_nothing_is_written():
    plain = engine()
    Base.metadata.create_all(plain)
    with sessionmaker(bind=plain, expire_on_commit=False)() as session:
        add_task(session, due_time="09:30", due_at=NOW)
        session.commit()
        with pytest.raises(RuntimeError, match=r"sqlite_savepoint_setup\(engine\).*before"):
            sweep(session, NOW, transactional=[FakeInbox()])
        session.rollback()
        assert session.scalar(select(func.count()).select_from(Ledger)) == 0
        with pytest.raises(RuntimeError, match="sqlite_savepoint_setup"):
            deliver_pending(session, ledger_model=Ledger, outbox_model=Outbox, notifiers={}, now=NOW,
                            commit=session.commit, task_model=Task)


def test_a_prepared_engine_works_and_rollback_leaves_no_rows(sq_factory):
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=NOW)
        session.commit()
        assert sweep(session, NOW, transactional=[FakeInbox()]).claimed == 1
        session.rollback()
        assert session.scalar(select(func.count()).select_from(Ledger)) == 0


def test_a_hand_made_setup_is_accepted():
    manual = engine()

    @event.listens_for(manual, "connect")
    def _connect(dbapi, record):
        dbapi.isolation_level = None

    @event.listens_for(manual, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(manual)
    with sessionmaker(bind=manual, expire_on_commit=False)() as session:
        add_task(session, due_time="09:30", due_at=NOW)
        session.commit()
        assert sweep(session, NOW, transactional=[FakeInbox()]).claimed == 1
        session.rollback()
        assert session.scalar(select(func.count()).select_from(Ledger)) == 0


def test_the_last_past_notice_of_a_far_east_zone_with_a_late_morning_is_still_a_candidate(sq_factory):
    zone = UserPrefs(time_zone="Pacific/Kiritimati", start_of_day=time(23, 30), end_of_day=time(23, 0))
    inbox = FakeInbox()
    with sq_factory() as session:
        # due 00:30 local on the 12th (UTC+14); the morning slot is 23:30, so seq 5 runs almost to day 7
        add_task(session, due_time="00:30", due_at=datetime(2026, 3, 11, 10, 30), due_date=date(2026, 3, 12))
        now = datetime(2026, 3, 18, 9, 0)  # 23:00 local on the 18th: 6.94 days after the due instant
        result = sweep(session, now, prefs=MapPrefs(default=zone), transactional=[inbox])
        assert result.claimed == 1
        assert [(n.stage, n.seq, n.last) for n in inbox.written] == [("past", 5, True)]


def test_a_task_far_past_its_series_is_not_even_loaded(sq_factory):
    with sq_factory() as session:
        add_task(session, "recent", due_time="09:30", due_at=NOW - timedelta(days=2))
        add_task(session, "just-outside", due_time="09:30", due_at=NOW - timedelta(days=8, hours=12))
        add_task(session, "ancient", due_time="09:30", due_at=NOW - timedelta(days=60))
        session.commit()
        session.expire_all()
        loaded = []

        def on_load(target, context):
            loaded.append(target.id)

        event.listen(Task, "load", on_load)
        try:
            sweep(session, NOW, transactional=[FakeInbox()])
        finally:
            event.remove(Task, "load", on_load)
        assert "recent" in loaded and "just-outside" not in loaded and "ancient" not in loaded


class SimpleTask:
    def __init__(self, remind):
        self.id, self.status, self.owner_user_id, self.assigned_user_id = "t", "open", "u", None
        self.due_date, self.due_time, self.due_at = date(2026, 3, 12), "09:30", NOW + timedelta(days=30)
        self.remind_minutes_before = remind


def test_the_default_lead_is_capped_at_the_maximum():
    prefs = UserPrefs(time_zone="UTC", lead_minutes=20000)
    task = SimpleTask(remind=-3)
    first = stage_times(task, prefs, "UTC", NOW)[0]
    assert first.stage == "close" and task.due_at - first.at == timedelta(minutes=MAX_LEAD_MINUTES)
    uncapped = UserPrefs(time_zone="UTC", lead_minutes=90)
    assert task.due_at - stage_times(task, uncapped, "UTC", NOW)[0].at == timedelta(minutes=90)


def test_the_upper_window_loads_exactly_the_maximum_lead_ahead_and_no_further(sq_factory):
    with sq_factory() as session:
        add_task(session, "edge", due_time="09:30", due_at=NOW + timedelta(minutes=MAX_LEAD_MINUTES))
        add_task(session, "beyond", due_time="09:30", due_at=NOW + timedelta(minutes=MAX_LEAD_MINUTES + 1))
        session.commit()
        session.expire_all()
        loaded = []

        def on_load(target, context):
            loaded.append(target.id)

        event.listen(Task, "load", on_load)
        try:
            sweep(session, NOW, transactional=[FakeInbox()])
        finally:
            event.remove(Task, "load", on_load)
        assert "edge" in loaded and "beyond" not in loaded
