"""The sweep on SQLite: the life of a task minute by minute, exactly-once, since, permissions, failure isolation."""
from datetime import date, datetime, timedelta

import pytest
from conftest import Ledger, Outbox, Task
from sqlalchemy import func, select
from support_sweep import FakeInbox, MapPrefs, load_cases, parse_z

from bond_tasks_py import UserPrefs
from bond_tasks_py.sweep import sweep_due

LA = UserPrefs(time_zone="America/Los_Angeles")
CREATED = datetime(2026, 3, 1)


def add_task(session, task_id="t1", *, owner="user-1", assigned=None, due_date=date(2026, 3, 12), due_time=None,
             due_at=None, status="open", remind=-3, priority=2, title="Call the plumber"):
    task = Task(id=task_id, owner_user_id=owner, created_by=owner, assigned_user_id=assigned, title=title,
                due_date=due_date, due_time=due_time, due_at=due_at, status=status, remind_minutes_before=remind,
                priority=priority, created_at=CREATED, updated_at=CREATED)
    session.add(task)
    session.flush()
    return task


def sweep(session, now, **kwargs):
    kwargs.setdefault("prefs", MapPrefs(default=LA))
    return sweep_due(session, task_model=Task, ledger_model=Ledger, now=now, **kwargs)


def ledger_keys(session):
    rows = session.execute(select(Ledger.task_id, Ledger.user_id, Ledger.stage, Ledger.seq, Ledger.status)
                           .order_by(Ledger.task_id, Ledger.user_id, Ledger.stage, Ledger.seq)).all()
    return [tuple(r) for r in rows]


def case(name):
    return next(c for c in load_cases() if c["name"] == name)


def expected_sends(name):
    return [(s["stage"], s["seq"], parse_z(s["send_at"])) for s in case(name)["stages"] if s["send_at"]]


def test_full_life_of_a_timed_and_a_date_only_task_minute_by_minute(sq_factory):
    timed, dated = case("timed_before_close"), case("dateonly_due_at_1701_sendable")
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, "timed", due_time="09:30", due_at=parse_z(timed["task"]["due_at"]))
        add_task(session, "dated", due_at=parse_z(dated["task"]["due_at"]))
        session.commit()
        clock, end = datetime(2026, 3, 12, 14, 0), datetime(2026, 3, 20, 14, 0)  # 8 days
        sent_at: dict[tuple, list] = {}
        while clock < end:
            before = len(inbox.written)
            sweep(session, clock, transactional=[inbox], channels=["chat"], outbox_model=Outbox)
            session.commit()
            for notice in inbox.written[before:]:
                sent_at.setdefault((notice.task_id, notice.stage, notice.seq), []).append(clock)
            clock += timedelta(minutes=1)
        for task_id, name in (("timed", "timed_before_close"), ("dated", "dateonly_due_at_1701_sendable")):
            got = sorted((stage, seq, times[0]) for (t, stage, seq), times in sent_at.items() if t == task_id)
            assert got == sorted(expected_sends(name)), task_id
        assert all(len(times) == 1 for times in sent_at.values())  # each exactly once
        assert session.scalar(select(func.count()).select_from(Outbox)) == len(inbox.written)
        last = [n for n in inbox.written if n.last]
        assert sorted(n.task_id for n in last) == ["dated", "timed"] and all(n.stage == "past" and n.seq == 5
                                                                                for n in last)


def test_two_sweeps_in_the_same_minute_make_one_row(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        first = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox])
        second = sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox])
        assert (first.claimed, second.claimed) == (1, 0)
        assert len(inbox.written) == 1 and ledger_keys(session) == [("t1", "user-1", "due", 0, "claimed")]


def test_a_missed_day_makes_seq_jump_without_a_flood(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox])  # due
        # nothing runs for two days, then a sweep at the next work day's morning
        result = sweep(session, datetime(2026, 3, 14, 15, 5), transactional=[inbox])
        assert result.claimed == 1
        assert [(n.stage, n.seq) for n in inbox.written] == [("due", 0), ("past", 2)]


def test_postponed_task_notifies_again(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        task = add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox])
        # postponing a day moves the token: a fresh due notice for the new time
        task.due_date, task.due_at = date(2026, 3, 13), datetime(2026, 3, 13, 16, 30)
        sweep(session, datetime(2026, 3, 13, 16, 30), transactional=[inbox])
        assert [(n.stage, n.seq) for n in inbox.written] == [("due", 0), ("due", 0)]
        assert inbox.written[0].notice_id != inbox.written[1].notice_id


def test_zone_change_on_a_date_only_task_does_not_notify_again(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        task = add_task(session, due_at=datetime(2026, 3, 13, 0, 0))  # 17:00 on the 12th in Los Angeles
        sweep(session, datetime(2026, 3, 13, 0, 0), transactional=[inbox])
        assert [(n.stage, n.seq) for n in inbox.written] == [("due", 0)]
        # the user moves to Auckland: the same date is now due at 17:00 there, a different instant
        task.due_at = datetime(2026, 3, 13, 4, 0)
        result = sweep(session, datetime(2026, 3, 13, 4, 0), transactional=[inbox],
                       prefs=MapPrefs(default=UserPrefs(time_zone="Pacific/Auckland")))
        assert result.claimed == 0 and len(inbox.written) == 1


def test_done_and_cancelled_stop_everything(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        task = add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        for status in ("done", "cancelled"):
            task.status = status
            assert sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox]).claimed == 0
            assert sweep(session, datetime(2026, 3, 13, 15, 0), transactional=[inbox]).claimed == 0
        assert inbox.written == [] and ledger_keys(session) == []


def test_since_records_skipped_rows_and_sends_nothing(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        since = datetime(2026, 3, 12, 16, 40)  # the due stage started before it
        result = sweep(session, datetime(2026, 3, 12, 16, 35), transactional=[inbox], channels=["chat"],
                       outbox_model=Outbox, since=since)
        assert (result.claimed, result.skipped, result.queued) == (0, 1, 0)
        assert inbox.written == [] and ledger_keys(session) == [("t1", "user-1", "due", 0, "skipped")]
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0
        # the next stage starts after since and is claimed
        later = sweep(session, datetime(2026, 3, 13, 15, 0), transactional=[inbox], since=since)
        assert later.claimed == 1 and [(n.stage, n.seq) for n in inbox.written] == [("past", 1)]


def test_actions_follow_permissions(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, owner="boss", assigned="worker", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox])
        sweep(session, datetime(2026, 3, 12, 16, 45), transactional=[inbox])
        by_user = {n.user_id: n for n in inbox.written}
        assert by_user["worker"].actions == ("done", "snooze")  # the assignee may not cancel
        assert [n.user_id for n in inbox.written if n.stage == "past"] == ["boss", "worker"]  # fixed order: user id
        past_owner = next(n for n in inbox.written if n.stage == "past" and n.user_id == "boss")
        assert past_owner.actions == ("done", "snooze", "cancel")
        assert past_owner.route == "/tasks/t1" and past_owner.kind == "task_due"


def test_max_past_is_respected_and_last_is_set(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        clock = datetime(2026, 3, 13, 15, 0)
        for _ in range(8):
            sweep(session, clock, transactional=[inbox], max_past=2)
            clock += timedelta(days=1)
        past = [(n.seq, n.last) for n in inbox.written if n.stage == "past"]
        assert past == [(1, False), (2, True)]
        assert "last" in inbox.written[-1].body


def test_assignee_and_owner_and_custom_recipients(sq_factory):
    class OnlyAuditor:
        def for_stage(self, session, task, stage):
            return ["auditor"] if stage == "past" else []

    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox], recipients=OnlyAuditor())
        assert inbox.written == []
        sweep(session, datetime(2026, 3, 13, 15, 0), transactional=[inbox], recipients=OnlyAuditor())
        assert [(n.user_id, n.stage) for n in inbox.written] == [("auditor", "past")]


def test_preferences_are_read_once_per_user_per_call(sq_factory):
    prefs = MapPrefs(default=LA)
    with sq_factory() as session:
        for i in range(5):
            add_task(session, f"t{i}", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), prefs=prefs)
        assert prefs.calls["user-1"] <= 2  # one for the sweep, at most one for the due-instant repair


def test_the_sweep_repairs_dated_tasks_without_due_at(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        task = add_task(session, "fix", due_time=None, due_at=None)
        result = sweep(session, datetime(2026, 3, 13, 0, 0), transactional=[inbox])
        assert result.repaired == 1 and task.due_at is not None
        assert [n.task_id for n in inbox.written] == ["fix"]  # 17:00 local on the date, then claimed


def test_custom_compose_and_default_wording(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, "a", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30), title="x" * 400)
        add_task(session, "b", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30), title="Pay\x00 rent")
        sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox])
        titles = {n.task_id: n.title for n in inbox.written}
        assert len(titles["a"]) == 255 and "\x00" not in titles["b"]
        inbox.written.clear()
        add_task(session, "c", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 31), transactional=[inbox],
              compose=lambda task, stage, seq, prefs: (f"T {task.id} {stage}", "B"))
        assert [(n.title, n.body) for n in inbox.written] == [("T c due", "B")]


def test_aware_since_and_now_are_normalised(sq_factory):
    from datetime import timezone

    plus_five = timezone(timedelta(hours=5))
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        # now 21:35 at UTC+5 is 16:35 UTC; since 21:20 at UTC+5 is 16:20 UTC, before the due stage: claimed.
        # Read as naive UTC values the wall clocks would put now (21:35) and since (21:20) far after the stage.
        now = datetime(2026, 3, 12, 21, 35, tzinfo=plus_five)
        inbox = FakeInbox()
        result = sweep(session, now, since=datetime(2026, 3, 12, 21, 20, tzinfo=plus_five), transactional=[inbox])
        assert (result.claimed, result.skipped) == (1, 0)
        assert session.scalar(select(Ledger.claimed_at)) == datetime(2026, 3, 12, 16, 35)  # the UTC instant
        assert inbox.written[0].created_at == datetime(2026, 3, 12, 16, 35)
        # a since after the stage (16:40 UTC, as 21:40 at UTC+5) skips it
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        result = sweep(session, datetime(2026, 3, 12, 16, 35), since=datetime(2026, 3, 12, 21, 40, tzinfo=plus_five))
        assert (result.claimed, result.skipped) == (0, 1)

def test_an_old_overdue_task_is_not_a_candidate_forever(sq_factory):
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2025, 1, 1, 16, 30))
        assert sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox]).claimed == 0
        assert inbox.written == []


def test_notice_recipients_is_owner_and_assignee_without_blanks():
    from types import SimpleNamespace

    from bond_tasks_py import notice_recipients

    assert notice_recipients(SimpleNamespace(owner_user_id="u1", assigned_user_id=None)) == {"u1"}
    assert notice_recipients(SimpleNamespace(owner_user_id="u1", assigned_user_id="u2")) == {"u1", "u2"}
    assert notice_recipients(SimpleNamespace(owner_user_id="u1", assigned_user_id="u1")) == {"u1"}


def test_done_is_withheld_when_permissions_refuse_completion(sq_factory):
    class NoComplete:
        def can_edit(self, task, user_id):
            return True

        def can_own(self, task, user_id):
            return True

        def can_complete(self, task, user_id):
            return False

    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 12, 16, 30), transactional=[inbox], permissions=NoComplete())
        assert inbox.written[0].actions == ("snooze", "cancel")


@pytest.mark.parametrize("since, skipped", [(datetime(2026, 3, 12, 16, 30), 0), (datetime(2026, 3, 12, 16, 31), 1)])
def test_a_stage_starting_exactly_at_since_is_claimed(sq_factory, since, skipped):
    with sq_factory() as session:
        add_task(session, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        result = sweep(session, datetime(2026, 3, 12, 16, 30), since=since, transactional=[FakeInbox()])
        assert (result.claimed, result.skipped) == (1 - skipped, skipped)


def test_a_recipients_seam_that_drops_a_user_is_obeyed(sq_factory):
    class OwnerOnly:
        def for_stage(self, session, task, stage):
            return [task.owner_user_id]

    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, owner="boss", assigned="worker", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        sweep(session, datetime(2026, 3, 13, 15, 0), transactional=[inbox], recipients=OwnerOnly())
        assert [n.user_id for n in inbox.written] == ["boss"]


def test_an_owner_still_gets_the_past_notice_when_the_assignee_has_no_current_stage(sq_factory):
    from datetime import time

    assignee = UserPrefs(time_zone="UTC", start_of_day=time(0, 0), end_of_day=time(23, 0))
    owner = UserPrefs(time_zone="America/Los_Angeles", start_of_day=time(20, 0), end_of_day=time(19, 0))
    prefs = MapPrefs({"asg": assignee, "boss": owner})
    inbox = FakeInbox()
    with sq_factory() as session:
        add_task(session, owner="boss", assigned="asg", due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
        # the assignee is past their series (seq 2 > max_past 1), the owner's late morning is still seq 1
        result = sweep(session, datetime(2026, 3, 14, 16, 0), prefs=prefs, transactional=[inbox], max_past=1)
        assert result.claimed == 1
        assert [(n.user_id, n.stage, n.seq) for n in inbox.written] == [("boss", "past", 1)]
