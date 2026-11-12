"""The claim and the delivery on PostgreSQL with real OS processes, one connection each."""
import multiprocessing
from datetime import date, datetime, timedelta

import pytest
from conftest import Ledger, Outbox, Task
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from support_sweep import (
    PG_META,
    PROBE_DELIVERIES,
    PROBE_NOTICES,
    pg_deliver_worker,
    pg_sweep_worker,
)

pytestmark = pytest.mark.postgres

NOW = datetime(2026, 3, 12, 16, 30)
TASKS = 2000
CTX = multiprocessing.get_context("spawn")


@pytest.fixture
def pg(pg_engine):
    PG_META.drop_all(pg_engine)
    PG_META.create_all(pg_engine)
    yield pg_engine
    PG_META.drop_all(pg_engine)


def url_of(engine):
    return engine.url.render_as_string(hide_password=False)


def seed(engine, count=TASKS):
    rows = [{"id": f"task-{i:05d}", "owner_user_id": f"user-{i % 50}", "created_by": "user-0", "title": f"Task {i}",
             "due_date": date(2026, 3, 12), "due_time": "09:30", "due_at": NOW, "status": "open",
             "remind_minutes_before": -3, "priority": 2} for i in range(count)]
    with Session(engine) as session:
        session.execute(Task.__table__.insert(), rows)
        session.commit()


def counts(engine):
    with Session(engine) as session:
        one = session.scalar
        return {
            "ledger": one(select(func.count()).select_from(Ledger)),
            "notices": one(select(func.count()).select_from(PROBE_NOTICES)),
            "distinct_notices": one(select(func.count(func.distinct(PROBE_NOTICES.c.notice_id)))),
            "outbox": one(select(func.count()).select_from(Outbox)),
            "deliveries": one(select(func.count()).select_from(PROBE_DELIVERIES)),
            "distinct_deliveries": one(select(func.count(func.distinct(PROBE_DELIVERIES.c.notice_id)))),
            "delivered": one(select(func.count()).select_from(Outbox).where(Outbox.delivered_at.is_not(None))),
        }


def run(target, args_list):
    queue = CTX.Queue()
    procs = [CTX.Process(target=target, args=(*args, queue)) for args in args_list]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=300)
    results = []
    while not queue.empty():
        results.append(queue.get())
    return procs, results


@pytest.mark.parametrize("workers,mode", [(2, "sweep"), (4, "sweep"), (4, "shuffled")])
def test_workers_claim_each_notice_exactly_once(pg, workers, mode):
    seed(pg)
    args = [(url_of(pg), NOW, 100 + 37 * i, mode, i) for i in range(workers)]  # different page boundaries
    procs, results = run(pg_sweep_worker, args)
    assert [r["error"] for r in results] == [None] * workers  # no deadlock or other error surfaced
    assert all(p.exitcode == 0 for p in procs)
    assert sum(r["claimed"] for r in results) == TASKS
    got = counts(pg)
    assert got["ledger"] == TASKS and got["notices"] == TASKS == got["distinct_notices"]
    assert got["outbox"] == TASKS


def test_a_crash_between_claim_and_commit_leaves_nothing(pg):
    seed(pg, 300)
    procs, _ = run(pg_sweep_worker, [(url_of(pg), NOW, 500, "crash_before_commit", 0)])
    assert procs[0].exitcode == 9
    got = counts(pg)
    assert (got["ledger"], got["notices"], got["outbox"]) == (0, 0, 0)
    # a later sweep claims everything
    procs, results = run(pg_sweep_worker, [(url_of(pg), NOW, 500, "sweep", 0)])
    assert results[0]["claimed"] == 300


def test_a_crash_after_commit_is_recovered_by_deliver_pending_exactly_once(pg):
    seed(pg, 300)
    procs, _ = run(pg_sweep_worker, [(url_of(pg), NOW, 500, "crash_after_commit", 0)])
    assert procs[0].exitcode == 9
    assert counts(pg)["ledger"] == 300 and counts(pg)["deliveries"] == 0
    # the next sweep claims nothing new, delivery finds the whole backlog
    _, results = run(pg_sweep_worker, [(url_of(pg), NOW, 500, "sweep", 0)])
    assert results[0]["claimed"] == 0
    _, delivered = run(pg_deliver_worker, [(url_of(pg), NOW, 40)])
    assert delivered[0]["sent"] == 300
    got = counts(pg)
    assert got["deliveries"] == got["distinct_deliveries"] == 300 and got["delivered"] == 300


def test_two_concurrent_deliver_pending_send_each_row_once(pg):
    seed(pg, 1000)
    run(pg_sweep_worker, [(url_of(pg), NOW, 500, "sweep", 0)])
    assert counts(pg)["outbox"] == 1000
    procs, results = run(pg_deliver_worker, [(url_of(pg), NOW, 25), (url_of(pg), NOW, 40)])
    assert [r["error"] for r in results] == [None, None] and all(p.exitcode == 0 for p in procs)
    assert sum(r["sent"] for r in results) == 1000
    got = counts(pg)
    assert got["deliveries"] == got["distinct_deliveries"] == 1000 and got["delivered"] == 1000


def pending_outbox(engine, count):
    """``count`` pending outbox rows (and their ledger rows) without tasks, inserted directly."""
    with Session(engine) as session:
        ids = [f"{i:032d}" for i in range(count)]
        session.execute(Ledger.__table__.insert(), [
            {"id": i, "task_id": f"t{n}", "user_id": "u", "stage": "due", "seq": 0, "deadline_token": "x",
             "status": "claimed", "stage_at": NOW, "claimed_at": NOW,
             "payload": {"kind": "task_due", "title": "t", "body": "b", "due_at": None, "priority": None,
                         "route": None, "actions": ["done", "snooze"], "last": False}}
            for n, i in enumerate(ids)])
        session.execute(Outbox.__table__.insert(), [
            {"ledger_id": i, "channel": "chat", "attempts": 0, "created_at": NOW + timedelta(seconds=n)}
            for n, i in enumerate(ids)])
        session.commit()


def test_limit_is_exact_and_two_concurrent_leasers_take_distinct_rows(pg):
    from support_sweep import FakeChannel

    from bond_tasks_py.outbox import deliver_pending

    pending_outbox(pg, 2000)
    with Session(pg) as one:
        r = deliver_pending(one, ledger_model=Ledger, outbox_model=Outbox, notifiers={"chat": FakeChannel(["retryable"])},
                            now=NOW, commit=one.commit, limit=100, task_model=None)
        assert r.leased == 100  # exactly the limit, not the whole table
    with Session(pg) as session:
        assert session.scalar(select(func.count()).select_from(Outbox).where(Outbox.attempts > 0)) == 100
        session.execute(Outbox.__table__.update().values(attempts=0, lease_until=None))
        session.commit()

    second = {}

    class Interloper:
        """While the first leaser still holds its (uncommitted) lease, a second one leases 100 more."""

        def send(self, session, notice):
            if not second:
                with Session(pg) as other:
                    second["result"] = deliver_pending(
                        other, ledger_model=Ledger, outbox_model=Outbox, notifiers={"chat": FakeChannel(["retryable"])},
                        now=NOW, commit=other.commit, limit=100, task_model=None)
            return "retryable"

    with Session(pg) as first:
        got = deliver_pending(first, ledger_model=Ledger, outbox_model=Outbox, notifiers={"chat": Interloper()},
                              now=NOW, commit=lambda: None, limit=100, task_model=None)  # the lease stays uncommitted
        assert got.leased == 100 and second["result"].leased == 100
        first.commit()
    with Session(pg) as session:
        leased = session.scalars(select(Outbox.attempts).where(Outbox.attempts > 0)).all()
        assert len(leased) == 200 and set(leased) == {1}  # 200 distinct rows, none leased twice


def test_aware_now_on_a_non_utc_session(pg_engine):
    from datetime import timezone

    from sqlalchemy import create_engine
    from support_sweep import FakeChannel

    from bond_tasks_py.outbox import deliver_pending
    from bond_tasks_py.retention import prune_ledger

    pending_outbox(pg_engine, 3)
    la = create_engine(url_of(pg_engine), connect_args={"options": "-c TimeZone=America/Los_Angeles"})
    aware = (NOW + timedelta(hours=5)).replace(tzinfo=timezone(timedelta(hours=5)))  # the instant NOW, at UTC+5
    try:
        with Session(la) as session:
            deliver_pending(session, ledger_model=Ledger, outbox_model=Outbox,
                            notifiers={"chat": FakeChannel(["retryable"] * 3)}, now=aware, commit=session.commit,
                            task_model=None)
            assert set(session.scalars(select(Outbox.lease_until))) == {NOW + timedelta(seconds=300)}
            # the ledger rows have no task: pruned, and an aware now does not shift the cut-off
            assert prune_ledger(session, task_model=Task, ledger_model=Ledger, outbox_model=Outbox, now=aware) == 3
            session.commit()
    finally:
        la.dispose()


def test_superseded_and_unrouted_on_postgres(pg):
    from support_sweep import FakeChannel

    from bond_tasks_py.outbox import deliver_pending

    seed(pg, 4)
    run(pg_sweep_worker, [(url_of(pg), NOW, 500, "sweep", 0)])
    with Session(pg) as session:
        session.execute(Task.__table__.update().where(Task.id == "task-00000").values(status="done"))
        session.commit()
        got = deliver_pending(session, ledger_model=Ledger, outbox_model=Outbox, notifiers={"chat": FakeChannel()},
                              now=NOW, commit=session.commit, task_model=Task)
        assert (got.leased, got.sent, got.superseded) == (4, 3, 1)


def test_prune_ledger_runs_on_postgres(pg):
    from bond_tasks_py.retention import prune_ledger

    seed(pg, 300)
    run(pg_sweep_worker, [(url_of(pg), NOW, 500, "sweep", 0)])
    with Session(pg) as session:
        args = {"task_model": Task, "ledger_model": Ledger, "outbox_model": Outbox}
        assert prune_ledger(session, now=NOW + timedelta(days=7), **args) == 0
        assert prune_ledger(session, now=NOW + timedelta(days=9), **args) == 300  # due rows older than 8 days
        session.commit()
    got = counts(pg)
    assert (got["ledger"], got["outbox"]) == (0, 0)


def test_due_at_round_trips_under_a_non_utc_session_time_zone(pg_engine):
    from sqlalchemy import create_engine

    url = pg_engine.url.render_as_string(hide_password=False)
    tokyo = create_engine(url, connect_args={"options": "-c TimeZone=Asia/Tokyo"})
    try:
        with Session(tokyo) as session:
            assert session.scalar(text("show timezone")) == "Asia/Tokyo"
            due = datetime(2026, 3, 12, 16, 30)
            session.add(Task(id="tz", owner_user_id="u", created_by="u", title="t", due_date=date(2026, 3, 12),
                             due_time="09:30", due_at=due, remind_minutes_before=-3))
            session.commit()
        with Session(pg_engine) as session:  # a different (default) session zone reads the same naive value
            assert session.scalar(select(Task.due_at).where(Task.id == "tz")) == due
        with Session(tokyo) as session:
            assert session.scalar(select(Task.due_at).where(Task.id == "tz")) == due
            assert session.scalar(select(Task.due_at).where(Task.id == "tz", Task.due_at <= due + timedelta())) == due
    finally:
        tokyo.dispose()
