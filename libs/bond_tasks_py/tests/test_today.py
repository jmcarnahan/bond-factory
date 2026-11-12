from datetime import date, datetime, time

import pytest
from conftest import Task
from support_read import FIXTURE_NOW, FIXTURE_ZONE, load_fixture, load_today_fixture, mk

from bond_tasks_py import TaskFilters, list_tasks, summary, today
from bond_tasks_py.timeutil import local_to_utc
from bond_tasks_py.today import TodayResult

NY = "America/New_York"
EMPTY = {"overdue": 0, "today": 0, "undated": 0, "done_today": 0}


def ids(rows):
    return [t.id for t in rows]


def run(session, now, zone, user="u1"):
    return today(session, task_model=Task, user_id=user, now=now, viewer_zone=zone)


def test_fixture_sections_and_counts(session):
    load_today_fixture(session, Task)
    expected = load_fixture("today.json")
    result = run(session, FIXTURE_NOW, FIXTURE_ZONE, user="user-1")
    for name in ("overdue", "today", "undated", "done_today"):
        assert ids(getattr(result, name)) == [t["id"] for t in expected[name]], name
    assert result.counts == expected["counts"]


def test_fixture_summary_counts_match(session):
    # today.json holds the four open tasks of summary.json's "open": 5 minus one task due on a later day
    load_today_fixture(session, Task)
    mk(session, Task, "task-later", owner="user-1", due=date(2026, 3, 20), due_time="10:00",
       due_at=local_to_utc(date(2026, 3, 20), time(10, 0), FIXTURE_ZONE))
    got = summary(session, task_model=Task, user_id="user-1", now=FIXTURE_NOW,
                  viewer_zone=FIXTURE_ZONE)
    assert got == load_fixture("summary.json")


def test_boundary_task_is_never_in_two_sections(session):
    mk(session, Task, "t", due=date(2026, 3, 11), due_time="17:00", due_at=local_to_utc(date(2026, 3, 11), time(17), NY))
    before = run(session, datetime(2026, 3, 11, 20, 59), NY)  # 16:59 in New York
    assert ids(before.today) == ["t"] and before.overdue == []
    after = run(session, datetime(2026, 3, 11, 21, 1), NY)  # 17:01
    assert ids(after.overdue) == ["t"] and after.today == []


def test_the_same_rows_read_by_viewers_in_two_zones(session):
    due_at = local_to_utc(date(2026, 3, 11), time(23), NY)  # 23:00 New York = 03:00Z on the 12th
    mk(session, Task, "late-ny", due=date(2026, 3, 11), due_time="23:00", due_at=due_at)
    now = datetime(2026, 3, 11, 5, 0)
    assert ids(run(session, now, NY).today) == ["late-ny"]
    # Honolulu is still on the 10th at that instant, so the task's day (the 11th) is a later day for it
    assert run(session, now, "Pacific/Honolulu").counts == EMPTY
    tokyo = run(session, datetime(2026, 3, 11, 20, 0), "Asia/Tokyo")  # 05:00 on the 12th, due at 12:00 the 12th
    assert ids(tokyo.today) == ["late-ny"]
    kiritimati = run(session, now, "Pacific/Kiritimati")  # 19:00 on the 11th, due 17:00 on the 12th: later day
    assert kiritimati.counts == EMPTY


def test_date_only_task_belongs_to_its_date_and_goes_overdue_at_its_instant(session):
    mk(session, Task, "d", due=date(2026, 3, 11), due_at=datetime(2026, 3, 12, 0, 0))
    assert ids(run(session, datetime(2026, 3, 11, 12, 0), FIXTURE_ZONE).today) == ["d"]
    assert ids(run(session, datetime(2026, 3, 11, 12, 0), "Asia/Tokyo").today) == ["d"]  # 21:00 on the 11th there
    late = run(session, datetime(2026, 3, 12, 0, 1), "Asia/Tokyo")  # the 12th there, due_at passed
    assert ids(late.overdue) == ["d"] and late.today == []


def test_later_day_is_in_no_list_and_sections_are_exclusive(session):
    mk(session, Task, "late", due=date(2026, 3, 1), due_time="09:00", due_at=datetime(2026, 3, 1, 17))
    mk(session, Task, "now", due=date(2026, 3, 11), due_time="15:00", due_at=datetime(2026, 3, 11, 22))
    mk(session, Task, "later", due=date(2026, 3, 12), due_time="09:00", due_at=datetime(2026, 3, 12, 16))
    mk(session, Task, "none")
    result = run(session, FIXTURE_NOW, FIXTURE_ZONE)
    placed = ids(result.overdue) + ids(result.today) + ids(result.undated) + ids(result.done_today)
    assert sorted(placed) == ["late", "none", "now"]


def test_done_today_uses_the_viewers_local_day(session):
    mk(session, Task, "in", status="done", completed_at=datetime(2026, 3, 11, 8, 0))  # 01:00 on the 11th in LA
    mk(session, Task, "before", status="done", completed_at=datetime(2026, 3, 11, 6, 59))  # 23:59 on the 10th
    mk(session, Task, "gone", status="cancelled", completed_at=datetime(2026, 3, 11, 9, 0))
    mk(session, Task, "open-one", completed_at=datetime(2026, 3, 11, 9, 0))
    assert ids(run(session, FIXTURE_NOW, FIXTURE_ZONE).done_today) == ["in"]
    assert ids(run(session, FIXTURE_NOW, "UTC").done_today) == ["before", "in"]


def test_only_my_tasks_owner_or_assignee(session):
    for id_, owner, assigned in (("mine", "u1", None), ("given", "u2", "u1"), ("theirs", "u2", None)):
        mk(session, Task, id_, owner=owner, assigned=assigned, due=date(2026, 3, 11), due_at=datetime(2026, 3, 12, 0))
    assert sorted(ids(run(session, FIXTURE_NOW, FIXTURE_ZONE).today)) == ["given", "mine"]


def test_sections_are_ordered_by_instant_nulls_last_then_newest(session):
    mk(session, Task, "b", due=date(2026, 3, 11), due_time="15:00", due_at=datetime(2026, 3, 11, 22, 0))
    mk(session, Task, "a", due=date(2026, 3, 11), due_time="13:30", due_at=datetime(2026, 3, 11, 20, 30))
    mk(session, Task, "eod", due=date(2026, 3, 11), due_at=datetime(2026, 3, 12, 0, 0))
    mk(session, Task, "old", created_at=datetime(2026, 3, 2))
    mk(session, Task, "new", created_at=datetime(2026, 3, 5))
    result = run(session, FIXTURE_NOW, FIXTURE_ZONE)
    assert ids(result.today) == ["a", "b", "eod"] and ids(result.undated) == ["new", "old"]


def test_dated_task_without_instant_falls_back_to_its_date(session):
    mk(session, Task, "stale", due=date(2026, 3, 10))
    mk(session, Task, "fresh", due=date(2026, 3, 11))
    result = run(session, FIXTURE_NOW, FIXTURE_ZONE)
    assert ids(result.overdue) == ["stale"] and ids(result.today) == ["fresh"] and result.undated == []


def test_empty_result(session):
    result = run(session, FIXTURE_NOW, "UTC")
    assert isinstance(result, TodayResult) and result.counts == EMPTY


@pytest.mark.parametrize("zone", [FIXTURE_ZONE, NY, "Asia/Tokyo", "UTC"])
def test_summary_and_today_agree(session, zone):
    mk(session, Task, "late", due=date(2026, 3, 1), due_time="09:00", due_at=datetime(2026, 3, 1, 17))
    mk(session, Task, "t1", due=date(2026, 3, 11), due_time="15:00", due_at=datetime(2026, 3, 11, 22))
    mk(session, Task, "eod", due=date(2026, 3, 11), due_at=datetime(2026, 3, 12, 0))
    mk(session, Task, "none")
    result = run(session, FIXTURE_NOW, zone)
    got = summary(session, task_model=Task, user_id="u1", now=FIXTURE_NOW, viewer_zone=zone)
    assert (got["overdue"], got["due_today"], got["no_date"]) == (
        result.counts["overdue"], result.counts["today"], result.counts["undated"])


def test_date_only_task_whose_date_passed_for_the_viewer_but_not_its_instant_is_today(session):
    # responsible user in Los Angeles: 17:00 on the 20th is 01:00Z on the 21st; a Sydney viewer is on the 21st
    mk(session, Task, "far", due=date(2026, 11, 20), due_at=datetime(2026, 11, 21, 1, 0))
    now = datetime(2026, 11, 21, 0, 0)
    for zone in ("Australia/Sydney", "America/Los_Angeles"):
        result = run(session, now, zone)
        assert ids(result.today) == ["far"] and result.overdue == [], zone
    got = summary(session, task_model=Task, user_id="u1", now=now,
                  viewer_zone="Australia/Sydney")
    assert got["due_today"] == 1 and got["overdue"] == 0
    after = run(session, datetime(2026, 11, 21, 1, 0, 1), "Australia/Sydney")
    assert ids(after.overdue) == ["far"] and after.today == []


def test_summary_open_equals_the_sections_plus_later_days(session):
    mk(session, Task, "far", due=date(2026, 11, 20), due_at=datetime(2026, 11, 21, 1, 0))
    mk(session, Task, "late", due=date(2026, 11, 1), due_at=datetime(2026, 11, 2, 1, 0))
    mk(session, Task, "later", due=date(2026, 11, 25), due_time="09:00", due_at=datetime(2026, 11, 25, 17))
    mk(session, Task, "none")
    now = datetime(2026, 11, 21, 0, 0)
    for zone in ("Australia/Sydney", "America/Los_Angeles", "UTC", "Pacific/Kiritimati"):
        got = summary(session, task_model=Task, user_id="u1", now=now, viewer_zone=zone)
        result = run(session, now, zone)
        upcoming = 1  # "later"
        assert got["open"] == got["overdue"] + got["due_today"] + got["no_date"] + upcoming, zone
        assert result.counts["today"] == got["due_today"], zone


def test_list_range_holding_today_includes_the_not_overdue_earlier_day_task(session):
    mk(session, Task, "far", due=date(2026, 11, 20), due_at=datetime(2026, 11, 21, 1, 0))
    now = datetime(2026, 11, 21, 0, 0)
    day = date(2026, 11, 21)
    rows, total = list_tasks(session, task_model=Task, user_id="u1", viewer_zone="Australia/Sydney", now=now,
                             filters=TaskFilters(due_from=day, due_to=day))
    assert ids(rows) == ["far"] and total == 1
    rows, _ = list_tasks(session, task_model=Task, user_id="u1", viewer_zone="Australia/Sydney", now=now,
                         filters=TaskFilters(due_from=date(2026, 11, 22), due_to=date(2026, 11, 22)))
    assert rows == []


def test_due_exactly_now_is_not_overdue_and_is_today(session):
    mk(session, Task, "t", due=date(2026, 3, 11), due_time="13:00", due_at=datetime(2026, 3, 11, 20, 0))
    result = run(session, FIXTURE_NOW, FIXTURE_ZONE)
    assert ids(result.today) == ["t"] and result.overdue == []
    got = summary(session, task_model=Task, user_id="u1", now=FIXTURE_NOW,
                  viewer_zone=FIXTURE_ZONE)
    assert got["overdue"] == 0 and got["due_today"] == 1


def test_done_today_window_is_start_inclusive_end_exclusive(session):
    mk(session, Task, "midnight", status="done", completed_at=datetime(2026, 3, 11, 7, 0))  # 00:00 on the 11th, LA
    mk(session, Task, "last-minute", status="done", completed_at=datetime(2026, 3, 12, 6, 59))
    mk(session, Task, "next-day", status="done", completed_at=datetime(2026, 3, 12, 7, 0))  # 00:00 on the 12th
    assert ids(run(session, FIXTURE_NOW, FIXTURE_ZONE).done_today) == ["last-minute", "midnight"]
    assert ids(run(session, datetime(2026, 3, 12, 8, 0), FIXTURE_ZONE).done_today) == ["next-day"]
