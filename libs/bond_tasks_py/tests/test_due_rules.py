"""One test per rule of docs/decisions/2026-11-11-due-instant.md, through the service and the due helpers."""

from datetime import date, datetime, time

import pytest
from conftest import NOW, Task
from support_core import MapPrefs

from bond_tasks_py import TaskCreate, TaskError, TaskUpdate, UserPrefs, service
from bond_tasks_py.due import backfill_due_at, compute_due_at, recompute_day_due

DAY = date(2026, 3, 12)  # New York is on daylight time (UTC-4), Los Angeles too (UTC-7)
USERS = {"u1", "u2", "u3"}


def make(session, owner="u1", actor=None, **kw):
    extra = {k: kw.pop(k) for k in ("writer_zone", "prefs") if k in kw}
    data = TaskCreate(**{"title": "T", **kw})
    return service.create(session, task_model=Task, owner_user_id=owner, actor_user_id=actor or owner, data=data,
                          now=NOW, user_exists=USERS.__contains__, **extra)


def edit(session, task, actor="u1", **kw):
    extra = {k: kw.pop(k) for k in ("writer_zone", "prefs") if k in kw}
    return service.update(session, task=task, actor_user_id=actor, data=TaskUpdate.model_validate(kw), now=NOW,
                          user_exists=USERS.__contains__, **extra)


def test_rule1_due_at_is_null_iff_undated_and_truncated_to_the_minute(session):
    assert make(session).due_at is None
    task = make(session, due_date=DAY, due_time="09:30", time_zone="America/New_York")
    assert task.due_at == datetime(2026, 3, 12, 13, 30) and task.due_at.second == 0
    edit(session, task, due_date=None)
    assert (task.due_at, task.due_time) == (None, None)


def test_rule3_timed_uses_the_zone_sent_else_the_writers_stored_zone_else_the_app_default(session):
    sent = make(session, due_date=DAY, due_time="09:30", time_zone="America/Los_Angeles",
                writer_zone="America/New_York")
    stored = make(session, due_date=DAY, due_time="09:30", writer_zone="America/New_York")
    default = make(session, due_date=DAY, due_time="09:30")
    assert sent.due_at == datetime(2026, 3, 12, 16, 30)
    assert stored.due_at == datetime(2026, 3, 12, 13, 30)
    assert default.due_at == datetime(2026, 3, 12, 9, 30)


def test_rule3_an_unknown_zone_name_is_a_coded_error(session):
    with pytest.raises(TaskError) as caught:
        make(session, due_date=DAY, due_time="09:30", time_zone="Mars/Olympus")
    assert caught.value.code == "invalid_time_zone"


def test_rule3_a_consistent_client_due_at_is_accepted_and_an_inconsistent_one_ignored():
    prefs = UserPrefs()
    kw = {"writer_zone": None, "responsible_prefs": prefs, "app_tz": "UTC"}
    ok = datetime(2026, 3, 12, 13, 30)  # offset -4:00 from 09:30
    assert compute_due_at(DAY, "09:30", client_due_at=ok, **kw) == ok
    for bad in (datetime(2026, 3, 12, 13, 37), datetime(2026, 3, 13, 9, 30), datetime(2026, 3, 11, 9, 30)):
        assert compute_due_at(DAY, "09:30", client_due_at=bad, **kw) == datetime(2026, 3, 12, 9, 30)
    # the zone name wins over a hint that disagrees with it, a hint that agrees is the same instant
    named = {**kw, "writer_zone": "America/New_York", "sent_zone": "America/New_York"}
    assert compute_due_at(DAY, "09:30", client_due_at=datetime(2026, 3, 12, 15, 30), **named) == ok
    assert compute_due_at(DAY, "09:30", client_due_at=ok, **named) == ok
    # never an error for a value of another kind (aware, far off)
    assert compute_due_at(DAY, "09:30", client_due_at=datetime(1900, 1, 1), **kw) == datetime(2026, 3, 12, 9, 30)


def test_rule3_through_create_a_device_hint_without_a_zone_is_used_when_plausible(session):
    task = make(session, due_date=DAY, due_time="09:30", due_at=datetime(2026, 3, 12, 13, 30))
    assert task.due_at == datetime(2026, 3, 12, 13, 30)


def test_rule3_a_plausible_hint_with_no_zone_sent_is_accepted_despite_a_stored_zone(session):
    # stored New York, the device is in Los Angeles: 09:00 PDT is 16:00Z (in this season), the hint is the truth
    hint = datetime(2026, 3, 12, 16, 0)
    task = make(session, due_date=DAY, due_time="09:00", due_at=hint, writer_zone="America/New_York")
    assert task.due_at == hint
    edit(session, task, due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30), writer_zone="America/New_York")
    assert task.due_at == datetime(2026, 3, 12, 16, 30)


def test_rule3_a_hint_and_a_sent_zone_that_disagree_the_zone_wins(session):
    task = make(session, due_date=DAY, due_time="09:00", due_at=datetime(2026, 3, 12, 16, 0),
                time_zone="America/New_York", writer_zone="America/Los_Angeles")
    assert task.due_at == datetime(2026, 3, 12, 13, 0)


def test_rule3_no_hint_uses_the_stored_zone(session):
    task = make(session, due_date=DAY, due_time="09:00", writer_zone="America/New_York")
    assert task.due_at == datetime(2026, 3, 12, 13, 0)


def test_rule4_date_only_ignores_a_client_due_at():
    kw = {"writer_zone": None, "responsible_prefs": UserPrefs(), "app_tz": "UTC"}
    assert compute_due_at(DAY, None, client_due_at=datetime(2026, 3, 12, 1, 0), **kw) == datetime(2026, 3, 12, 17, 0)


def test_rule4_new_york_writer_assigns_to_a_los_angeles_user_with_no_stored_zone(session):
    task = make(session, assigned_user_id="u2", due_date=DAY, time_zone="America/New_York",
                writer_zone="America/New_York", prefs=MapPrefs())
    assert task.due_at == datetime(2026, 3, 12, 17, 0)  # 17:00 in the app default zone (UTC), not New York's


def test_rule4_the_same_with_a_stored_zone_and_end_of_day(session):
    prefs = MapPrefs(u2=UserPrefs(time_zone="America/Los_Angeles", end_of_day=time(16, 30)))
    task = make(session, assigned_user_id="u2", due_date=DAY, time_zone="America/New_York", prefs=prefs)
    assert task.due_at == datetime(2026, 3, 12, 23, 30)  # 16:30 PDT


def test_rule4_the_writer_who_is_the_responsible_user_uses_the_zone_sent_when_none_is_stored(session):
    task = make(session, due_date=DAY, time_zone="America/New_York", prefs=MapPrefs())
    assert task.due_at == datetime(2026, 3, 12, 21, 0)  # 17:00 EDT
    stored = MapPrefs(u1=UserPrefs(time_zone="America/Los_Angeles"))
    again = make(session, due_date=DAY, time_zone="America/New_York", prefs=stored)
    assert again.due_at == datetime(2026, 3, 13, 0, 0)  # the stored zone beats the one sent


def test_rule4_a_task_write_never_stores_a_zone(session):
    task = make(session, due_date=DAY, time_zone="America/New_York")
    assert not hasattr(task, "time_zone") and "time_zone" not in Task.__table__.columns


def test_rule5_a_patch_that_resends_the_same_date_and_time_from_another_zone_keeps_due_at(session):
    task = make(session, due_date=DAY, due_time="09:30", time_zone="America/New_York")
    before = task.due_at
    edit(session, task, due_date="2026-03-12", due_time="09:30", time_zone="America/Los_Angeles")
    assert task.due_at == before


def test_rule5_a_patch_changing_only_the_title_keeps_due_at(session):
    task = make(session, due_date=DAY, due_time="09:30", time_zone="America/New_York")
    before = task.due_at
    edit(session, task, title="Renamed", time_zone="America/Los_Angeles")
    assert task.due_at == before


def test_rule5_changing_the_time_or_the_date_recomputes(session):
    task = make(session, due_date=DAY, due_time="09:30", time_zone="America/New_York")
    edit(session, task, due_time="10:00", time_zone="America/New_York")
    assert task.due_at == datetime(2026, 3, 12, 14, 0)
    edit(session, task, due_date="2026-03-13", time_zone="America/New_York")
    assert task.due_at == datetime(2026, 3, 13, 14, 0)


def test_rule5_clearing_the_time_turns_a_timed_task_into_an_end_of_day_task(session):
    task = make(session, due_date=DAY, due_time="09:30", time_zone="America/New_York")
    edit(session, task, due_time=None, time_zone="America/New_York")
    # the writer is the responsible user with no stored zone, so the zone sent is used: 17:00 EDT
    assert task.due_at == datetime(2026, 3, 12, 21, 0)


def test_rule5_reassigning_a_date_only_task_moves_due_at_to_the_new_users_end_of_day_and_zone(session):
    prefs = MapPrefs(u2=UserPrefs(time_zone="America/Los_Angeles", end_of_day=time(18, 0)))
    task = make(session, due_date=DAY, prefs=prefs)
    assert task.due_at == datetime(2026, 3, 12, 17, 0)
    edit(session, task, assigned_user_id="u2", prefs=prefs)
    assert task.due_at == datetime(2026, 3, 13, 1, 0)  # 18:00 PDT


def test_rule5_reassigning_a_timed_task_does_not_move_it(session):
    prefs = MapPrefs(u2=UserPrefs(time_zone="Asia/Tokyo"))
    task = make(session, due_date=DAY, due_time="09:30", time_zone="America/New_York")
    before = task.due_at
    edit(session, task, assigned_user_id="u2", prefs=prefs)
    assert task.assigned_user_id == "u2" and task.due_at == before


def test_rule6_a_replayed_create_is_a_noop(session):
    first = make(session, id="dev-1", title="A", due_date=DAY, due_time="09:30", time_zone="America/New_York")
    again = make(session, id="dev-1", title="B", due_date=date(2027, 1, 1), time_zone="Asia/Tokyo")
    assert again is first and (first.title, first.due_at) == ("A", datetime(2026, 3, 12, 13, 30))


def test_rule6_a_replayed_patch_applies_the_rules_against_the_current_settings(session):
    task = make(session, due_date=DAY)  # 17:00 UTC with the defaults
    later = MapPrefs(u1=UserPrefs(end_of_day=time(18, 0)))
    # the first delivery was lost; the patch arrives now and sees the new end of day
    edit(session, task, due_date="2026-03-13", prefs=later)
    assert task.due_at == datetime(2026, 3, 13, 18, 0)
    # a second delivery sends the same values: nothing differs, so nothing moves
    edit(session, task, due_date="2026-03-13", prefs=MapPrefs(u1=UserPrefs(end_of_day=time(19, 0))))
    assert task.due_at == datetime(2026, 3, 13, 18, 0)


def test_rule7_a_time_that_does_not_exist_moves_forward_and_an_ambiguous_one_takes_the_first(session):
    gap = make(session, due_date=date(2026, 3, 8), due_time="02:30", time_zone="America/New_York")
    fold = make(session, due_date=date(2026, 11, 1), due_time="01:30", time_zone="America/New_York")
    assert gap.due_at == datetime(2026, 3, 8, 7, 30)  # 03:30 EDT
    assert fold.due_at == datetime(2026, 11, 1, 5, 30)  # the first 01:30, still EDT


def test_rule7_the_end_of_day_on_a_change_day_uses_the_offset_in_force(session):
    prefs = MapPrefs(u1=UserPrefs(time_zone="America/New_York"))
    spring = make(session, due_date=date(2026, 3, 8), prefs=prefs)
    assert spring.due_at == datetime(2026, 3, 8, 21, 0)  # 17:00 EDT


def test_rule11_the_default_reminder_for_a_new_task_is_minus_three_and_an_explicit_value_is_kept(session):
    assert make(session, due_date=DAY).remind_minutes_before == -3
    assert make(session, due_date=DAY, remind_minutes_before=-2).remind_minutes_before == -2
    assert make(session, due_date=DAY, remind_minutes_before=30).remind_minutes_before == 30


def test_rule_priority_is_stored_as_sent_and_null_clears_it(session):
    task = make(session, priority=3)
    assert task.priority == 3
    edit(session, task, priority=1)
    assert task.priority == 1
    edit(session, task, priority=None)
    assert task.priority is None
    with pytest.raises(ValueError):
        TaskUpdate.model_validate({"priority": 4})


def test_recompute_day_due_changes_only_that_users_open_date_only_tasks(session):
    mine = make(session, due_date=DAY)
    assigned_away = make(session, due_date=DAY, assigned_user_id="u2")
    assigned_to_me = make(session, owner="u2", due_date=DAY, assigned_user_id="u1")
    timed = make(session, due_date=DAY, due_time="09:30")
    done = make(session, due_date=DAY)
    service.complete(session, done, "u1", NOW)
    others = make(session, owner="u2", due_date=DAY)
    undated = make(session)
    before = {t.id: t.due_at for t in (assigned_away, timed, done, others, undated)}
    prefs = MapPrefs(u1=UserPrefs(time_zone="America/Los_Angeles", end_of_day=time(18, 0)))
    count = recompute_day_due(session, task_model=Task, user_id="u1", prefs=prefs, tz="UTC", now=NOW)
    assert count == 2
    assert mine.due_at == assigned_to_me.due_at == datetime(2026, 3, 13, 1, 0)
    assert {t.id: t.due_at for t in (assigned_away, timed, done, others, undated)} == before
    assert recompute_day_due(session, task_model=Task, user_id="u1", prefs=prefs, tz="UTC", now=NOW) == 0


def test_backfill_due_at_fills_dated_tasks_without_one_oldest_first_up_to_the_limit(session):
    tasks = []
    for n in range(3):
        task = make(session, due_date=DAY)
        task.created_at = datetime(2026, 1, 1, 0, n)
        task.due_at = None
        tasks.append(task)
    undated = make(session)
    session.flush()
    prefs = MapPrefs()
    assert backfill_due_at(session, task_model=Task, prefs=prefs, tz="UTC", now=NOW, limit=2) == 2
    assert [t.due_at is not None for t in tasks] == [True, True, False]
    assert backfill_due_at(session, task_model=Task, prefs=prefs, tz="UTC", now=NOW) == 1
    assert tasks[2].due_at == datetime(2026, 3, 12, 17, 0) and undated.due_at is None
    assert backfill_due_at(session, task_model=Task, prefs=prefs, tz="UTC", now=NOW) == 0


def test_backfill_uses_the_creators_zone_for_a_timed_task(session):
    task = make(session, due_date=DAY, due_time="09:30", writer_zone="Asia/Tokyo")
    task.due_at = None
    prefs = MapPrefs(u1=UserPrefs(time_zone="America/New_York"))
    assert backfill_due_at(session, task_model=Task, prefs=prefs, tz="UTC", now=NOW) == 1
    assert task.due_at == datetime(2026, 3, 12, 13, 30)
