"""Claim failures, batching, idle sweeps and the SQLite savepoint setup."""
from datetime import datetime

import pytest
from conftest import Outbox
from sqlalchemy import event, func, select
from support_sweep import FakeInbox
from test_sweep import add_task, ledger_keys, sweep


def test_a_permanently_bad_row_writes_nothing_and_never_stops_the_others(sq_factory):
    inbox = FakeInbox(bad_users={"bad"})
    with sq_factory() as session:
        add_task(session, "t1", owner="good1", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        add_task(session, "t2", owner="bad", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        add_task(session, "t3", owner="good2", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        result = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox], channels=["chat"],
                       outbox_model=Outbox)
        assert (result.claimed, result.queued, result.errors) == (2, 2, 1)
        assert ledger_keys(session) == [("t1", "good1", "due", 0, "claimed"), ("t3", "good2", "due", 0, "claimed")]
        assert sorted(n.user_id for n in inbox.written) == ["good1", "good2"]
        assert session.scalar(select(func.count()).select_from(Outbox)) == 2  # none for the bad row
        # every later sweep still tries the bad row, still claims nothing else twice, and still reports it
        again = sweep(session, datetime(2026, 3, 12, 16, 31), transactional=[inbox])
        assert (again.claimed, again.errors) == (0, 1) and len(inbox.written) == 2
        add_task(session, "t4", owner="good3", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        later = sweep(session, datetime(2026, 3, 12, 16, 32), transactional=[inbox])
        assert (later.claimed, later.errors) == (1, 1)


def test_a_notifier_down_for_one_sweep_loses_no_notice(sq_factory, caplog):
    class Flaky:
        def __init__(self):
            self.up, self.written = False, []

        def write(self, session, notices):
            if not self.up:
                raise ConnectionError("inbox down: secret title")
            self.written.extend(notices)

    inbox = Flaky()
    with sq_factory() as session:
        for i in range(10):
            add_task(session, f"t{i}", owner=f"u{i}", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        down = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox], channels=["chat"],
                     outbox_model=Outbox)
        assert (down.claimed, down.errors) == (0, 10)
        assert ledger_keys(session) == [] and session.scalar(select(func.count()).select_from(Outbox)) == 0
        assert len(caplog.records) == 10 and all("ConnectionError" in r.getMessage() for r in caplog.records)
        assert not any("secret" in r.getMessage() for r in caplog.records)  # ids and class only, never the text
        inbox.up = True
        up = sweep(session, datetime(2026, 3, 12, 16, 31), transactional=[inbox], channels=["chat"],
                   outbox_model=Outbox)  # still within the due window
        assert (up.claimed, up.errors) == (10, 0)
        assert len(inbox.written) == 10 and len({n.notice_id for n in inbox.written}) == 10
        assert sweep(session, datetime(2026, 3, 12, 16, 32), transactional=[inbox]).claimed == 0


def test_an_idle_sweep_issues_no_insert(sq_factory):
    inbox = FakeInbox()
    statements = []
    with sq_factory() as session:
        for i in range(500):
            add_task(session, f"t{i:04d}", owner=f"u{i % 20}", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        assert sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox]).claimed == 500
        session.commit()
        event.listen(session.get_bind(), "before_cursor_execute", lambda *a: statements.append(a[2]))
        again = sweep(session, datetime(2026, 3, 12, 16, 31), transactional=[inbox])
        assert again.claimed == 0 and len(inbox.written) == 500
    inserts = [s for s in statements if s.lstrip().upper().startswith("INSERT")]
    assert inserts == []
    assert len(statements) < 30  # a few selects, not a statement per task


def test_recipients_are_asked_only_for_the_current_stage(sq_factory):
    asked = []

    class Spy:
        def for_stage(self, session, task, stage):
            asked.append(stage)
            return ["user-1"]

    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), recipients=Spy())
        assert asked == ["due"]
        asked.clear()
        sweep(session, datetime(2026, 3, 13, 15, 0), recipients=Spy())  # past: once, for owner and assignee alike
        assert asked == ["past"]


def test_a_whole_batch_failure_leaves_no_ledger_row(sq_factory):
    class AlwaysRaises:
        def write(self, session, notices):
            raise RuntimeError("down")

    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        result = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[AlwaysRaises()])
        assert (result.claimed, result.errors) == (0, 1) and ledger_keys(session) == []


def test_batches_split_large_claims(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        for i in range(200):
            add_task(session, f"t{i:04d}", owner=f"u{i}", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        result = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox], limit=70)
        assert result.claimed == 200 and inbox.batches == [70, 70, 60]  # one claim per page of tasks


def test_a_page_is_claimed_in_batches_of_at_most_eighty(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        for i in range(200):
            add_task(session, f"t{i:04d}", owner=f"u{i}", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        assert sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox]).claimed == 200
        assert inbox.batches == [80, 80, 40]


def test_channels_without_an_outbox_model_is_an_error(sq_factory):
    with sq_factory() as session, pytest.raises(ValueError):
        sweep(session, datetime(2026, 3, 12, 16, 30), channels=["chat"])


def test_sqlite_savepoint_setup_keeps_the_sweep_uncommitted():
    from conftest import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from bond_tasks_py.dialect import sqlite_savepoint_setup

    engine = sqlite_savepoint_setup(
        create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool))
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        session.commit()
        assert sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[FakeInbox()]).claimed == 1
        session.rollback()  # the sweep committed nothing: its rows go away
        assert ledger_keys(session) == []


def test_no_statement_exceeds_900_bind_parameters_with_three_channels(sq_factory):
    sizes = []
    with sq_factory() as session:
        for i in range(80):
            add_task(session, f"t{i:03d}", owner=f"u{i}", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        event.listen(session.get_bind(), "before_cursor_execute",
                     lambda conn, cur, statement, parameters, *rest: sizes.append(len(parameters)))
        result = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[FakeInbox()],
                       channels=["a", "b", "c"], outbox_model=Outbox)
        assert (result.claimed, result.queued) == (80, 240)
        assert session.scalar(select(func.count()).select_from(Outbox)) == 240
    assert max(sizes) <= 900


def test_compose_is_not_called_for_notices_already_claimed(sq_factory):
    calls = []

    def compose(task, stage, seq, prefs):
        calls.append(task.id)
        return "T", "B"

    with sq_factory() as session:
        for i in range(5):
            add_task(session, f"t{i}", owner=f"u{i}", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), compose=compose)
        assert len(calls) == 5
        sweep(session, datetime(2026, 3, 12, 16, 31), compose=compose)
        assert len(calls) == 5  # the second sweep composed nothing
        add_task(session, "late", owner="u9", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 32), compose=compose)
        assert calls[5:] == ["late"]  # only the new notice


def test_a_conflicting_outbox_row_does_not_break_the_claim(sq_factory):
    from bond_tasks_py.stages import deadline_token, notice_id

    with sq_factory() as session:
        task = add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        nid = notice_id("t1", "user-1", "due", 0, deadline_token(task))
        session.execute(Outbox.__table__.insert().values(ledger_id=nid, channel="chat", attempts=0,
                                                         created_at=datetime(2026, 3, 12)))
        result = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[FakeInbox()], channels=["chat"],
                       outbox_model=Outbox)
        assert (result.claimed, result.errors) == (1, 0)


def test_a_row_another_worker_won_is_not_written_again(sq_factory, monkeypatch):
    from bond_tasks_py import sweep as sweep_module

    first, second = FakeInbox(), FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[first], channels=["chat"], outbox_model=Outbox)
        # the existence check misses it (another worker committed in between): the insert is the arbiter
        monkeypatch.setattr(sweep_module, "existing_ids", lambda *a, **k: set())
        result = sweep(session, datetime(2026, 3, 12, 16, 31), transactional=[second], channels=["chat"],
                       outbox_model=Outbox)
        assert (result.claimed, result.queued) == (0, 0) and second.written == []
        assert session.scalar(select(func.count()).select_from(Outbox)) == 1
