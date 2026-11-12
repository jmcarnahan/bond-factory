"""grandfather_before, backfill open_only, Notice.attempt and at_most_once."""
from datetime import date, datetime, timedelta

import pytest
from conftest import Outbox, Task
from sqlalchemy import select
from support_sweep import FakeChannel, FakeInbox, MapPrefs
from test_outbox import NOW, deliver, row, seed
from test_sweep import add_task, ledger_keys, sweep

from bond_tasks_py import UserPrefs
from bond_tasks_py.due import backfill_due_at

DUE = datetime(2026, 3, 12, 16, 30)


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)])
def gf_factory(request, sq_factory):
    """The same lifecycle on SQLite and, when BOND_TEST_POSTGRES_URL is set, on PostgreSQL."""
    if request.param == "sqlite":
        return sq_factory
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=request.getfixturevalue("pg_engine"), expire_on_commit=False)


def test_grandfather_skips_following_mornings(gf_factory):
    inbox = FakeInbox()
    with gf_factory() as session:
        add_task(session, owner="boss", assigned="worker", due_time="09:30", due_at=DUE)
        session.commit()
        activation = DUE + timedelta(minutes=5)
        clock = activation
        for _ in range(8):  # eight mornings, more than max_past
            result = sweep(session, clock, transactional=[inbox], grandfather_before=activation + timedelta(hours=1))
            session.commit()
            assert result.claimed == 0
            clock = datetime.combine(clock.date() + timedelta(days=1), datetime.min.time()) + timedelta(hours=15)
        assert inbox.written == []
        statuses = {r[4] for r in ledger_keys(session)}
        assert statuses == {"skipped"}
        stages = {(r[1], r[2], r[3]) for r in ledger_keys(session)}
        assert ("boss", "past", 5) in stages and ("worker", "due", 0) in stages and ("worker", "past", 5) in stages


def test_task_due_after_cutoff_still_notifies(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=DUE)
        result = sweep(session, DUE, transactional=[inbox], grandfather_before=DUE - timedelta(hours=1))
        assert result.claimed == 1 and [(n.stage, n.seq) for n in inbox.written] == [("due", 0)]


def test_task_due_exactly_at_the_cutoff_is_not_grandfathered(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=DUE)
        assert sweep(session, DUE, transactional=[inbox], grandfather_before=DUE).claimed == 1


def test_grandfather_none_unchanged(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=DUE)
        sweep(session, DUE + timedelta(minutes=5), transactional=[inbox])
        sweep(session, datetime(2026, 3, 13, 15, 0), transactional=[inbox])
        assert [(n.stage, n.seq) for n in inbox.written] == [("due", 0), ("past", 1)]


def test_backfill_open_only(session):
    prefs = MapPrefs(default=UserPrefs(time_zone="UTC"))
    for task_id, status in (("a", "open"), ("b", "done"), ("c", "cancelled")):
        session.add(Task(id=task_id, owner_user_id="u1", created_by="u1", title="x", due_date=date(2026, 3, 12),
                         status=status, remind_minutes_before=-3, priority=2, created_at=NOW, updated_at=NOW))
    session.flush()
    kwargs = {"task_model": Task, "prefs": prefs, "tz": "UTC", "now": NOW}
    assert backfill_due_at(session, open_only=True, **kwargs) == 1
    assert [t.id for t in session.scalars(select(Task).where(Task.due_at.is_not(None)))] == ["a"]
    assert backfill_due_at(session, **kwargs) == 2  # the default still fills the rest


def test_notice_attempt_is_1_then_2_after_expired_lease(gf_factory):
    class Crash(BaseException):
        pass

    chat = FakeChannel(raises=[Crash()])
    with gf_factory() as session:
        seed(session)
        try:
            deliver(session, {"chat": chat})
        except Crash:
            pass
        session.rollback()
        deliver(session, {"chat": chat}, now=NOW + timedelta(seconds=301))
        assert [n.attempt for n in chat.sent] == [1, 2]


def test_notice_attempt_defaults_to_1_off_the_outbox():
    from bond_tasks_py import Notice
    assert Notice("i", "t", "u", "due", 0, "task_due", "T", "B", None, None, None, NOW, (), False).attempt == 1


class Probe:
    """Records, at send time, whether ``delivered_at`` is stamped and how many commits have happened."""

    def __init__(self, commits, raises=None, verdict="ok", channel="chat"):
        self.commits, self.raises, self.verdict, self.channel = commits, raises, verdict, channel
        self.stamped, self.sent = [], []

    def send(self, session, notice):
        stamp = session.scalar(select(Outbox.delivered_at).where(Outbox.channel == self.channel))
        self.stamped.append((stamp is not None, len(self.commits)))
        self.sent.append(notice)
        if self.raises:
            raise self.raises
        return self.verdict


def run(session, commits, notifiers, now=NOW, **kwargs):
    def commit():
        commits.append(1)
        session.commit()

    return deliver(session, notifiers, now=now, commit=commit, **kwargs)


def test_at_most_once_stamps_before_send(sq_factory):
    with sq_factory() as session:
        seed(session)
        commits = []
        probe = Probe(commits)
        result = run(session, commits, {"chat": probe}, at_most_once=["chat"])
        assert result.sent == 1 and probe.stamped == [(True, 2)]  # lease commit, then the stamp commit, then send
        assert row(session).delivered_at is not None


def test_at_most_once_crash_loses_the_notice_instead_of_repeating_it(sq_factory):
    class Crash(BaseException):
        pass

    with sq_factory() as session:
        seed(session)
        commits = []
        probe = Probe(commits, raises=Crash())
        try:
            run(session, commits, {"chat": probe}, at_most_once=["chat"])
        except Crash:
            pass
        session.rollback()
        assert run(session, commits, {"chat": probe}, now=NOW + timedelta(days=1), at_most_once=["chat"]).leased == 0
        assert len(probe.sent) == 1


def test_at_most_once_retryable_is_not_retried(sq_factory):
    with sq_factory() as session:
        seed(session)
        commits = []
        probe = Probe(commits, verdict="retryable")
        result = run(session, commits, {"chat": probe}, at_most_once=["chat"])
        assert (result.failed, result.retryable) == (1, 0)
        assert run(session, commits, {"chat": probe}, now=NOW + timedelta(days=1), at_most_once=["chat"]).leased == 0


def test_default_delivery_stamps_after_the_send(sq_factory):
    with sq_factory() as session:
        seed(session)
        commits = []
        probe = Probe(commits)
        run(session, commits, {"chat": probe})
        assert probe.stamped == [(False, 1)] and row(session).delivered_at is not None


def test_at_most_once_only_touches_the_named_channel(sq_factory):
    with sq_factory() as session:
        seed(session, channels=("chat", "mail"))
        commits = []
        once, normal = Probe(commits), Probe(commits, channel="mail")
        run(session, commits, {"chat": once, "mail": normal}, at_most_once=["chat"])
        assert once.stamped == [(True, 2)] and normal.stamped[0][0] is False
