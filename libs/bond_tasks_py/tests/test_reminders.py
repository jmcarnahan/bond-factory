from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

import pytest
from conftest import NOW, Base, FakeScheduler, Task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bond_tasks_py import (
    TaskCreate,
    TaskUpdate,
    cancel_reminder,
    compute_remind_at,
    dedupe_key,
    fire_reminder,
    schedule_reminder,
    service,
)

DAY = date(2026, 11, 10)


def make(session, tz="UTC", **fields):
    return service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t", **fields), now=NOW, tz=tz)


def test_no_reminder_encoding():
    assert compute_remind_at(DAY, "10:00", -2, "UTC") is None


def test_no_date_means_no_reminder():
    assert compute_remind_at(None, None, 15, "UTC") is None


def test_morning_of_is_eight_local():
    assert compute_remind_at(DAY, "17:00", -1, "UTC") == datetime(2026, 11, 10, 8, 0)
    assert compute_remind_at(DAY, None, -1, "UTC") == datetime(2026, 11, 10, 8, 0)


def test_minutes_before_the_due_time():
    assert compute_remind_at(DAY, "10:00", 30, "UTC") == datetime(2026, 11, 10, 9, 30)
    assert compute_remind_at(DAY, "10:00", 0, "UTC") == datetime(2026, 11, 10, 10, 0)


def test_minutes_before_crosses_midnight():
    assert compute_remind_at(DAY, "00:10", 30, "UTC") == datetime(2026, 11, 9, 23, 40)


def test_a_date_only_task_counts_as_due_at_eight():
    assert compute_remind_at(DAY, None, 60, "UTC") == datetime(2026, 11, 10, 7, 0)


def test_timezone_shifts_the_utc_instant():
    # November: Los Angeles is UTC-8 (standard time), Berlin UTC+1
    assert compute_remind_at(DAY, "10:00", 0, "America/Los_Angeles") == datetime(2026, 11, 10, 18, 0)
    assert compute_remind_at(DAY, "10:00", -1, "Europe/Berlin") == datetime(2026, 11, 10, 7, 0)


def test_daylight_saving_changes_the_offset():
    # 2026-03-08 is the US spring-forward day; 10:00 local is UTC-7 after the change
    assert compute_remind_at(date(2026, 3, 8), "10:00", 0, "America/Los_Angeles") == datetime(2026, 3, 8, 17, 0)
    assert compute_remind_at(date(2026, 3, 7), "10:00", 0, "America/Los_Angeles") == datetime(2026, 3, 7, 18, 0)


def test_unknown_timezone_raises():
    with pytest.raises(ZoneInfoNotFoundError):
        compute_remind_at(DAY, "10:00", 0, "Not/AZone")


def test_create_computes_remind_at(session):
    task = make(session, due_date=DAY, due_time="10:00", remind_minutes_before=15)
    assert task.remind_at == datetime(2026, 11, 10, 9, 45)


def test_schedule_enqueues_at_remind_at_under_the_dedupe_key(session):
    task = make(session, due_date=DAY, due_time="10:00", remind_minutes_before=15)
    scheduler = FakeScheduler()
    when = schedule_reminder(session, task, scheduler, tz="UTC")
    assert when == datetime(2026, 11, 10, 9, 45)
    assert scheduler.jobs == {f"task_reminder:{task.id}": {
        "job_type": "task_reminder", "payload": {"task_id": task.id}, "run_at": when}}
    assert dedupe_key(task.id) == f"task_reminder:{task.id}"


def test_reschedule_cancels_the_previous_job(session):
    task = make(session, due_date=DAY, due_time="10:00", remind_minutes_before=15)
    scheduler = FakeScheduler()
    schedule_reminder(session, task, scheduler, tz="UTC")
    service.update(session, task=task, actor_user_id="u1", now=NOW,
                   data=TaskUpdate.model_validate({"due_time": "11:00"}))
    schedule_reminder(session, task, scheduler, tz="UTC")
    assert scheduler.cancelled == [dedupe_key(task.id)] * 2
    assert next(iter(scheduler.jobs.values()))["run_at"] == datetime(2026, 11, 10, 10, 45)
    assert len(scheduler.jobs) == 1


def test_turning_the_reminder_off_cancels_without_enqueuing(session):
    task = make(session, due_date=DAY, due_time="10:00", remind_minutes_before=15)
    scheduler = FakeScheduler()
    schedule_reminder(session, task, scheduler, tz="UTC")
    service.update(session, task=task, actor_user_id="u1", now=NOW,
                   data=TaskUpdate.model_validate({"remind_minutes_before": -2}))
    assert schedule_reminder(session, task, scheduler, tz="UTC") is None
    assert scheduler.jobs == {}


def test_done_task_is_not_scheduled(session):
    task = make(session, due_date=DAY, due_time="10:00", remind_minutes_before=0)
    service.complete(session, task, "u1", NOW)
    scheduler = FakeScheduler()
    assert schedule_reminder(session, task, scheduler, tz="UTC") is None
    assert scheduler.jobs == {}


def test_cancel_reminder_uses_the_key():
    scheduler = FakeScheduler()
    cancel_reminder(None, "abc", scheduler)
    assert scheduler.cancelled == ["task_reminder:abc"]


def test_fire_notifies_once(session):
    task = make(session, due_date=DAY, due_time="10:00", remind_minutes_before=0)
    seen = []
    due = task.remind_at
    assert fire_reminder(session, Task, task.id, seen.append, now=due + timedelta(minutes=1)) is True
    assert fire_reminder(session, Task, task.id, seen.append, now=due + timedelta(minutes=2)) is False
    assert len(seen) == 1 and task.reminded_at == due + timedelta(minutes=1)


def test_fire_before_it_is_due_does_nothing(session):
    task = make(session, due_date=DAY, due_time="10:00", remind_minutes_before=0)
    seen = []
    assert fire_reminder(session, Task, task.id, seen.append, now=task.remind_at - timedelta(seconds=1)) is False
    assert seen == [] and task.reminded_at is None


def test_fire_skips_missing_done_and_unreminded_tasks(session):
    seen = []
    assert fire_reminder(session, Task, "gone", seen.append, now=NOW) is False
    done = make(session, due_date=date(2026, 11, 8), due_time="09:00", remind_minutes_before=0)
    service.complete(session, done, "u1", NOW)
    plain = make(session, due_date=date(2026, 11, 8), due_time="09:00")
    assert fire_reminder(session, Task, done.id, seen.append, now=NOW) is False
    assert fire_reminder(session, Task, plain.id, seen.append, now=NOW) is False
    assert seen == []


def test_fire_retries_when_notify_fails(session):
    task = make(session, due_date=date(2026, 11, 8), due_time="09:00", remind_minutes_before=0)

    def boom(_):
        raise RuntimeError("push down")

    with pytest.raises(RuntimeError):
        fire_reminder(session, Task, task.id, boom, now=NOW)
    assert task.reminded_at is None
    seen = []
    assert fire_reminder(session, Task, task.id, seen.append, now=NOW) is True and len(seen) == 1


def test_moving_the_reminder_rearms_it(session):
    task = make(session, due_date=date(2026, 11, 8), due_time="09:00", remind_minutes_before=0)
    fire_reminder(session, Task, task.id, lambda t: None, now=NOW)
    assert task.reminded_at is not None
    service.update(session, task=task, actor_user_id="u1", now=NOW,
                   data=TaskUpdate.model_validate({"due_date": date(2026, 11, 12)}))
    assert task.reminded_at is None and task.remind_at == datetime(2026, 11, 12, 9, 0)


def test_two_workers_firing_at_once_notify_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/fire.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as setup:
        task = make(setup, due_date=date(2026, 11, 8), due_time="09:00", remind_minutes_before=0)
        setup.commit()
    seen = []
    with factory() as first, factory() as second:
        second.get(Task, task.id)  # the slower worker has already read the row: reminded_at is still empty for it
        assert fire_reminder(first, Task, task.id, seen.append, now=NOW) is True
        first.commit()
        assert fire_reminder(second, Task, task.id, seen.append, now=NOW) is False
        second.commit()
    assert len(seen) == 1
    with factory() as check:
        assert check.get(Task, task.id).reminded_at == NOW


def test_a_released_claim_can_be_retaken(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/fire2.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as setup:
        task = make(setup, due_date=date(2026, 11, 8), due_time="09:00", remind_minutes_before=0)
        setup.commit()

    def boom(_):
        raise RuntimeError("down")

    with factory() as s, pytest.raises(RuntimeError):
        fire_reminder(s, Task, task.id, boom, now=NOW)
        s.commit()
    with factory() as s:
        s.commit()
        assert fire_reminder(s, Task, task.id, lambda t: None, now=NOW) is True
