"""prune_ledger on SQLite: what goes, what stays, and that a re-sweep after pruning claims nothing new."""
from datetime import datetime, timedelta

from conftest import Ledger, Outbox, Task
from sqlalchemy import func, select
from support_sweep import FakeInbox
from test_sweep import add_task, ledger_keys, sweep

from bond_tasks_py.retention import prune_ledger

DUE = datetime(2026, 3, 12, 16, 30)


def prune(session, now, **kwargs):
    return prune_ledger(session, task_model=Task, ledger_model=Ledger, outbox_model=Outbox, now=now, **kwargs)


def run_days(session, start, end, inbox, step=timedelta(minutes=15)):
    clock = start
    while clock <= end:
        sweep(session, clock, transactional=[inbox], channels=["chat"], outbox_model=Outbox)
        clock += step


def outbox_count(session):
    return session.scalar(select(func.count()).select_from(Outbox))


def test_closed_tasks_are_pruned_after_closed_days_with_their_outbox_rows(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        task = add_task(session, due_time="09:30", due_at=DUE)
        run_days(session, DUE, DUE + timedelta(days=2), inbox)
        assert ledger_keys(session) and outbox_count(session)
        task.status, task.updated_at = "done", datetime(2026, 3, 14)
        total = len(ledger_keys(session))
        assert prune(session, datetime(2026, 4, 10)) == 0  # closed 27 days ago: kept
        assert prune(session, datetime(2026, 4, 14)) == total
        assert ledger_keys(session) == [] and outbox_count(session) == 0


def test_rows_of_a_task_that_is_gone_are_pruned(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        task = add_task(session, due_time="09:30", due_at=DUE)
        sweep(session, DUE, transactional=[inbox], channels=["chat"], outbox_model=Outbox)
        session.delete(task)
        session.flush()
        assert prune(session, DUE) == 1
        assert ledger_keys(session) == [] and outbox_count(session) == 0


def test_open_task_close_and_due_rows_go_after_eight_days_past_rows_keep_the_newest(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=DUE)
        run_days(session, DUE - timedelta(hours=2), DUE + timedelta(days=2, hours=1), inbox)
        stages = [(r[2], r[3]) for r in ledger_keys(session)]
        assert stages == [("close", 0), ("due", 0), ("past", 0), ("past", 1), ("past", 2)]
        # nine days after the claims: close and due are gone; old past rows go, the newest past stays
        deleted = prune(session, DUE + timedelta(days=9))
        assert deleted == 4
        assert [(r[2], r[3]) for r in ledger_keys(session)] == [("past", 2)]
        assert outbox_count(session) == 1
        # an hour later nothing more
        assert prune(session, DUE + timedelta(days=9, hours=1)) == 0


def test_recent_rows_are_not_touched(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=DUE)
        run_days(session, DUE - timedelta(hours=2), DUE + timedelta(days=1, hours=1), inbox)
        before = ledger_keys(session)
        assert prune(session, DUE + timedelta(days=1, hours=2)) == 0
        assert ledger_keys(session) == before


def test_after_pruning_a_resweep_claims_nothing_new(sq_factory):
    """The two unsafe prunes (all past rows; close rows of a task still in its close stage) would re-send."""
    inbox = FakeInbox()
    with sq_factory() as session:
        # a task with a one-week close window, due in the future: its close row must survive any prune
        add_task(session, "far", due_time="09:30", due_at=DUE + timedelta(days=7), remind=7 * 24 * 60)
        # an overdue task in the middle of its mornings
        add_task(session, "late", due_time="09:30", due_at=DUE)
        now = DUE + timedelta(days=5, hours=1)  # 8:30 local on the 17th: past seq 5 (the last) is current
        run_days(session, DUE - timedelta(hours=2), now, inbox, step=timedelta(hours=1))
        count = len(inbox.written)
        assert any(r[0] == "far" and r[2] == "close" for r in ledger_keys(session))
        prune(session, now + timedelta(days=1), closed_days=30)
        prune(session, now)
        again = sweep(session, now, transactional=[inbox])
        assert again.claimed == 0 and len(inbox.written) == count
        # and pruning at a later time than the close claim never removes the claim while it is current
        assert prune(session, DUE + timedelta(days=6)) >= 0
        assert sweep(session, DUE + timedelta(days=6), transactional=[inbox]).claimed == 0


def test_pruning_close_rows_of_a_task_still_in_close_would_resend(sq_factory):
    """A close row of a task still in its (week-long) close stage is kept, so the sweep does not send it again."""
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=DUE + timedelta(days=7), remind=7 * 24 * 60)
        sweep(session, DUE, transactional=[inbox])
        assert len(inbox.written) == 1
        late = DUE + timedelta(days=6, hours=23)
        assert prune(session, late) == 0
        assert sweep(session, late, transactional=[inbox]).claimed == 0


def test_rows_of_an_old_deadline_go_after_eight_days(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        task = add_task(session, due_time="09:30", due_at=DUE)
        sweep(session, DUE, transactional=[inbox], channels=["chat"], outbox_model=Outbox)
        # the task is postponed two weeks: the old due row belongs to a deadline that is gone
        task.due_date, task.due_at = DUE.date() + timedelta(days=14), DUE + timedelta(days=14)
        sweep(session, DUE + timedelta(days=14), transactional=[inbox], channels=["chat"], outbox_model=Outbox)
        assert len(ledger_keys(session)) == 2
        assert prune(session, DUE + timedelta(days=7)) == 0  # claimed 7 days ago: kept
        assert prune(session, DUE + timedelta(days=14, hours=1)) == 1  # only the old-token row: the new one is 1h old
        remaining = session.scalars(select(Ledger)).all()
        assert len(remaining) == 1 and remaining[0].stage_at == DUE + timedelta(days=14)
        assert outbox_count(session) == 1


def test_an_aware_now_is_normalised(sq_factory):
    from datetime import timezone

    plus_five = timezone(timedelta(hours=5))
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, "gone-soon", due_time="09:30", due_at=DUE)
        sweep(session, DUE, transactional=[inbox])
        session.execute(Task.__table__.update().values(status="done", updated_at=datetime(2026, 3, 13)))
        # 2026-04-12 00:30 at UTC+5 is 2026-04-11 19:30 UTC: the task closed 29 days and 19 hours ago, so it stays;
        # read as a naive UTC value (the wall clock) it would be 30 days and 30 minutes, and be pruned
        assert prune(session, datetime(2026, 4, 12, 0, 30, tzinfo=plus_five)) == 0
        assert prune(session, datetime(2026, 4, 12, 7, 0, tzinfo=plus_five)) == 1  # 02:00 UTC: past the 30 days


def test_the_old_deadline_rule_reads_the_ledger_in_chunks(sq_factory, monkeypatch):
    from sqlalchemy import event

    from bond_tasks_py import retention

    monkeypatch.setattr(retention, "READ_CHUNK", 2)
    inbox = FakeInbox()
    reads = []
    with sq_factory() as session:
        tasks = [add_task(session, f"t{i}", owner=f"u{i}", due_time="09:30", due_at=DUE) for i in range(5)]
        morning = datetime(2026, 3, 13, 15, 0)
        sweep(session, morning, transactional=[inbox])  # past 1: kept by the newest-sequence rule
        for task in tasks:  # all five postponed: all five old rows are stale
            task.due_date, task.due_at = DUE.date() + timedelta(days=3), DUE + timedelta(days=3)
        session.flush()
        event.listen(session.get_bind(), "before_cursor_execute",
                     lambda conn, cur, statement, *rest: reads.append(statement) if "JOIN" in statement else None)
        assert prune(session, morning + timedelta(days=9)) == 5
    assert len(reads) == 3  # pages of 2, 2 and 1 rows
