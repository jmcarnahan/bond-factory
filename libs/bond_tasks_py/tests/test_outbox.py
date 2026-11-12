"""deliver_pending on SQLite: leases, verdicts, retries, crashes, unknown channels."""
from datetime import datetime, timedelta, timezone

from conftest import Ledger, Outbox, Task
from sqlalchemy import func, select
from support_sweep import FakeChannel
from test_sweep import add_task, sweep

from bond_tasks_py.outbox import deliver_pending

NOW = datetime(2026, 3, 12, 16, 30)


def seed(session, channels=("chat",)):
    add_task(session, due_time="09:30", due_at=NOW)
    sweep(session, NOW, channels=list(channels), outbox_model=Outbox)
    session.commit()


def deliver(session, notifiers, now=NOW, **kwargs):
    kwargs.setdefault("commit", session.commit)
    kwargs.setdefault("task_model", Task)
    return deliver_pending(session, ledger_model=Ledger, outbox_model=Outbox, notifiers=notifiers, now=now, **kwargs)


def row(session, channel="chat"):
    session.expire_all()
    return session.execute(select(Outbox).where(Outbox.channel == channel)).scalar_one()


def test_ok_stamps_delivered_and_the_notice_is_rebuilt_from_the_ledger(sq_factory):
    chat = FakeChannel()
    with sq_factory() as session:
        seed(session)
        result = deliver(session, {"chat": chat})
        assert (result.leased, result.sent) == (1, 1)
        notice = chat.sent[0]
        ledger = session.execute(select(Ledger)).scalar_one()
        assert (notice.notice_id, notice.stage, notice.user_id, notice.route) == (ledger.id, "due", "user-1",
                                                                                  "/tasks/t1")
        assert notice.actions == ("done", "snooze", "cancel") and notice.due_at == NOW
        assert row(session).delivered_at == NOW and row(session).attempts == 1
        assert deliver(session, {"chat": chat}).leased == 0 and len(chat.sent) == 1


def test_commit_is_called_after_the_lease_and_before_any_send(sq_factory):
    events = []
    chat = FakeChannel()
    original = chat.send
    chat.send = lambda session, notice: (events.append("send"), original(session, notice))[1]
    with sq_factory() as session:
        seed(session)
        deliver(session, {"chat": chat}, commit=lambda: (events.append("commit"), session.commit()))
    assert events == ["commit", "send", "commit"]


def test_retryable_then_ok(sq_factory):
    chat = FakeChannel(verdicts=["retryable", "ok"])
    with sq_factory() as session:
        seed(session)
        first = deliver(session, {"chat": chat})
        assert (first.retryable, first.sent) == (1, 0)
        assert row(session).delivered_at is None and row(session).failed_at is None
        # still leased: nothing to do until the lease ends
        assert deliver(session, {"chat": chat}, now=NOW + timedelta(seconds=10)).leased == 0
        second = deliver(session, {"chat": chat}, now=NOW + timedelta(seconds=301))
        assert (second.leased, second.sent) == (1, 1) and row(session).attempts == 2


def test_unregistered_and_failed_are_final(sq_factory):
    with sq_factory() as session:
        seed(session, channels=("a", "b"))
        result = deliver(session, {"a": FakeChannel(["unregistered"]), "b": FakeChannel(["failed"])})
        assert (result.unregistered, result.failed, result.sent) == (1, 1, 0)
        assert row(session, "a").failed_at == NOW and row(session, "b").failed_at == NOW
        assert deliver(session, {"a": FakeChannel(), "b": FakeChannel()}, now=NOW + timedelta(days=1)).leased == 0


def test_max_attempts_gives_up(sq_factory):
    chat = FakeChannel(verdicts=["retryable"] * 5)
    with sq_factory() as session:
        seed(session)
        now = NOW
        results = []
        for _ in range(3):
            results.append(deliver(session, {"chat": chat}, now=now, max_attempts=3))
            now += timedelta(seconds=301)
        assert [(r.retryable, r.failed) for r in results] == [(1, 0), (1, 0), (0, 1)]
        assert row(session).failed_at is not None and "retryable" in row(session).last_error
        assert deliver(session, {"chat": chat}, now=now, max_attempts=3).leased == 0 and len(chat.sent) == 3


def test_a_raising_notifier_is_retryable(sq_factory):
    chat = FakeChannel(raises=[RuntimeError("boom")])
    with sq_factory() as session:
        seed(session)
        result = deliver(session, {"chat": chat})
        assert result.retryable == 1 and "boom" in row(session).last_error
        assert deliver(session, {"chat": chat}, now=NOW + timedelta(seconds=301)).sent == 1


def test_a_crash_between_lease_and_send_redelivers_after_the_lease_ends(sq_factory):
    class Crash(BaseException):
        pass

    chat = FakeChannel(raises=[Crash()])
    with sq_factory() as session:
        seed(session)
        try:
            deliver(session, {"chat": chat})
        except Crash:
            pass
        session.rollback()
        assert row(session).lease_until == NOW + timedelta(seconds=300) and row(session).delivered_at is None
        assert deliver(session, {"chat": chat}, now=NOW + timedelta(seconds=100)).leased == 0
        again = deliver(session, {"chat": chat}, now=NOW + timedelta(seconds=301))
        assert again.sent == 1 and len(chat.sent) == 2 and chat.sent[0].notice_id == chat.sent[1].notice_id


def test_rows_leased_after_their_attempts_ran_out_fail_without_a_send(sq_factory):
    chat = FakeChannel()
    with sq_factory() as session:
        seed(session)
        session.execute(Outbox.__table__.update().values(attempts=3))
        session.commit()
        result = deliver(session, {"chat": chat}, max_attempts=3)
        assert (result.failed, chat.sent) == (1, [])


def test_unknown_channel_is_left_pending_and_counted(sq_factory):
    chat = FakeChannel()
    with sq_factory() as session:
        seed(session, channels=("chat", "mail"))
        result = deliver(session, {"chat": chat})
        assert (result.leased, result.sent, result.retryable, result.unrouted) == (1, 1, 0, 1)
        mail = row(session, "mail")
        assert mail.attempts == 0 and mail.lease_until is None and mail.failed_at is None
        later = deliver(session, {"chat": chat, "mail": FakeChannel()}, now=NOW + timedelta(minutes=1))
        assert later.sent == 1


def test_limit_leases_in_order_and_a_pruned_ledger_row_fails(sq_factory):
    chat = FakeChannel()
    with sq_factory() as session:
        for i in range(3):
            add_task(session, f"t{i}", owner=f"u{i}", due_time="09:30", due_at=NOW)
        sweep(session, NOW, channels=["chat"], outbox_model=Outbox)
        session.commit()
        assert deliver(session, {"chat": chat}, limit=2).leased == 2
        session.execute(Ledger.__table__.delete())
        session.commit()
        last = deliver(session, {"chat": chat})
        assert (last.leased, last.failed, len(chat.sent)) == (1, 1, 2)


def test_a_channel_without_a_notifier_fails_after_seven_days(sq_factory):
    with sq_factory() as session:
        seed(session, channels=("mail",))
        early = deliver(session, {"chat": FakeChannel()}, now=NOW + timedelta(days=6))
        assert (early.unrouted, early.failed) == (1, 0)
        late = deliver(session, {"chat": FakeChannel()}, now=NOW + timedelta(days=8))
        assert (late.unrouted, late.failed) == (0, 1)
        failed = row(session, "mail")
        assert failed.failed_at == NOW + timedelta(days=8) and failed.last_error == "no notifier"


def test_limit_leases_exactly_that_many(sq_factory):
    with sq_factory() as session:
        for i in range(30):
            add_task(session, f"t{i:02d}", owner=f"u{i}", due_time="09:30", due_at=NOW)
        sweep(session, NOW, channels=["chat"], outbox_model=Outbox)
        session.commit()
        assert deliver(session, {"chat": FakeChannel()}, limit=7).leased == 7
        assert session.scalar(select(func.count()).select_from(Outbox).where(Outbox.lease_until.is_not(None))) == 7
        assert deliver(session, {"chat": FakeChannel()}, limit=250).leased == 23  # more than one key chunk is fine


def test_a_row_is_stamped_and_committed_before_the_next_send(sq_factory):
    class Boom(BaseException):
        pass

    chat = FakeChannel(raises=[None, None, None, Boom()])
    with sq_factory() as session:
        for i in range(5):
            add_task(session, f"t{i}", owner=f"u{i}", due_time="09:30", due_at=NOW)
        sweep(session, NOW, channels=["chat"], outbox_model=Outbox)
        session.commit()
        try:
            deliver(session, {"chat": chat})
        except Boom:
            pass
        session.rollback()
        session.expire_all()
        assert session.scalar(select(func.count()).select_from(Outbox).where(Outbox.delivered_at.is_not(None))) == 3
        again = deliver(session, {"chat": chat}, now=NOW + timedelta(seconds=301))
        assert again.sent == 2
        ok_ids = [n.notice_id for n in chat.sent]
        first_three = ok_ids[:3]
        assert all(ok_ids.count(i) == 1 for i in first_three)  # no duplicate of the stamped rows
        assert len(chat.sent) == 6  # 4 first run (one died) + 2 after the lease ended


def test_superseded_rows_are_not_sent(sq_factory):
    with sq_factory() as session:
        done = add_task(session, "done", owner="a", due_time="09:30", due_at=NOW)
        moved = add_task(session, "moved", owner="b", due_time="09:30", due_at=NOW)
        add_task(session, "gone", owner="c", due_time="09:30", due_at=NOW)
        cancelled = add_task(session, "cancelled", owner="d", due_time="09:30", due_at=NOW)
        add_task(session, "same", owner="e", due_time="09:30", due_at=NOW)
        sweep(session, NOW, channels=["chat"], outbox_model=Outbox)
        session.commit()
        done.status, cancelled.status = "done", "cancelled"
        moved.due_at = NOW + timedelta(days=1)
        session.execute(Task.__table__.delete().where(Task.id == "gone"))
        session.commit()
        chat = FakeChannel()
        result = deliver(session, {"chat": chat}, task_model=Task)
        assert (result.leased, result.sent, result.superseded) == (5, 1, 4)
        assert [n.task_id for n in chat.sent] == ["same"]
        session.expire_all()
        rows = session.scalars(select(Outbox).where(Outbox.last_error == "superseded")).all()
        assert len(rows) == 4 and all(r.failed_at is not None and r.delivered_at is None for r in rows)


def test_without_task_model_nothing_is_checked(sq_factory):
    with sq_factory() as session:
        task = add_task(session, due_time="09:30", due_at=NOW)
        sweep(session, NOW, channels=["chat"], outbox_model=Outbox)
        session.commit()
        task.status = "done"
        assert deliver(session, {"chat": FakeChannel()}, task_model=None).sent == 1


def test_task_model_is_a_required_argument(sq_factory):
    import pytest

    with sq_factory() as session:
        seed(session)
        with pytest.raises(TypeError):
            deliver_pending(session, ledger_model=Ledger, outbox_model=Outbox, notifiers={"chat": FakeChannel()},
                            now=NOW, commit=session.commit)


def test_an_aware_now_is_normalised(sq_factory):
    plus_five = timezone(timedelta(hours=5))
    with sq_factory() as session:
        seed(session)
        aware = (NOW + timedelta(hours=5)).replace(tzinfo=plus_five)  # the same instant as NOW
        assert deliver(session, {"chat": FakeChannel(["retryable"])}, now=aware).retryable == 1
        assert row(session).lease_until == NOW + timedelta(seconds=300)  # not shifted by five hours
