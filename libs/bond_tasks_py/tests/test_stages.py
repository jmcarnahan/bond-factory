"""Stages against the shared fixture (68 cases), plus the token and the quiet-hours edge rules."""
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from support_sweep import fmt_z, load_cases, parse_z, prefs_from_json, task_from_json

from bond_tasks_py import UserPrefs
from bond_tasks_py.quiet import in_quiet_hours, next_work_start, sendable
from bond_tasks_py.stages import (
    MAX_LEAD_MINUTES,
    current_stage,
    deadline_token,
    effective_zone,
    notice_id,
    stage_times,
)
from bond_tasks_py.sweep import default_recipients

CASES = load_cases()


def test_fixture_has_all_cases():
    assert len(CASES) == 68


def _view(case):
    task, prefs = task_from_json(case["task"]), prefs_from_json(case["prefs"])
    return task, prefs, parse_z(case["now"]), case["user_id"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fixture_case(case):
    task, prefs, now, user = _view(case)
    max_past = case["max_past"]
    assert effective_zone(prefs, case["app_tz"]) == case["effective_zone"]
    assert deadline_token(task) == case["token"]

    stages = [s for s in stage_times(task, prefs, case["app_tz"], now, max_past=max_past)
              if user in default_recipients(task, s.stage)]
    got = [{"stage": s.stage, "seq": s.seq, "at": fmt_z(s.at), "last": s.last, "send_at": fmt_z(s.send_at)}
           for s in stages]
    assert got == case["stages"]

    current = current_stage(task, prefs, case["app_tz"], now, max_past=max_past)
    if current is not None and user not in default_recipients(task, current.stage):
        current = None
    expected = case["current"]
    if expected is None:
        assert current is None
        assert case["sendable"] is False
        assert case["notice_id"] is None
        return
    assert {"stage": current.stage, "seq": current.seq, "at": fmt_z(current.at), "last": current.last} == expected
    zone = effective_zone(prefs, case["app_tz"])
    assert sendable(task, current.stage, prefs, zone, now) is case["sendable"]
    assert notice_id(task.id, user, current.stage, current.seq, case["token"]) == case["notice_id"]


def test_token_forms():
    timed = SimpleNamespace(due_date=date(2026, 3, 12), due_time="09:30", due_at=datetime(2026, 3, 12, 16, 30))
    assert deadline_token(timed) == "29555550"
    timed.due_at = datetime(2026, 3, 12, 16, 31)  # moved a minute: a new token
    assert deadline_token(timed) == "29555551"
    timed.due_at = None
    assert deadline_token(timed) == ""
    dated = SimpleNamespace(due_date=date(2026, 3, 12), due_time=None, due_at=datetime(2026, 3, 13, 0, 0))
    assert deadline_token(dated) == "2026-03-12"
    dated.due_at = datetime(2026, 4, 1)  # a zone change moves due_at, not the token
    assert deadline_token(dated) == "2026-03-12"
    assert deadline_token(SimpleNamespace(due_date=None, due_time=None, due_at=None)) == ""


def test_lead_is_capped():
    task = task_from_json(CASES[0]["task"])
    task.remind_minutes_before = 10_000_000
    prefs = UserPrefs(time_zone="UTC")
    first = stage_times(task, prefs, "UTC", datetime(2026, 1, 1))[0]
    assert first.stage == "close" and task.due_at - first.at == timedelta(minutes=MAX_LEAD_MINUTES)


def test_invalid_user_zone_falls_back_to_app_zone():
    assert effective_zone(UserPrefs(time_zone="Not/AZone"), "Europe/Paris") == "Europe/Paris"
    assert effective_zone(UserPrefs(time_zone=None), "Europe/Paris") == "Europe/Paris"


def test_quiet_hours_edges():
    prefs = UserPrefs(start_of_day=time(8, 0), end_of_day=time(17, 0))
    assert not in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 17, 0))
    assert in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 17, 1))
    assert in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 7, 59))
    assert not in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 8, 0))
    assert in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 3, 0))


def test_quiet_hours_work_day_across_midnight_and_equal_times():
    night = UserPrefs(start_of_day=time(22, 0), end_of_day=time(6, 0))
    assert not in_quiet_hours(night, "UTC", datetime(2026, 3, 12, 23, 0))
    assert not in_quiet_hours(night, "UTC", datetime(2026, 3, 12, 6, 0))
    assert in_quiet_hours(night, "UTC", datetime(2026, 3, 12, 12, 0))
    assert not in_quiet_hours(night, "UTC", datetime(2026, 3, 12, 22, 0))
    same = UserPrefs(start_of_day=time(8, 0), end_of_day=time(8, 0))
    assert not any(in_quiet_hours(same, "UTC", datetime(2026, 3, 12, h, 30)) for h in range(24))


def test_quiet_hours_use_the_zone():
    prefs = UserPrefs()
    # 02:00 UTC is 19:00 the day before in Los Angeles (daylight time): quiet there, quiet in UTC too
    assert in_quiet_hours(prefs, "America/Los_Angeles", datetime(2026, 7, 1, 2, 0))
    # 16:00 UTC is 09:00 in Los Angeles: work day there, and also in UTC
    assert not in_quiet_hours(prefs, "America/Los_Angeles", datetime(2026, 7, 1, 16, 0))
    # 04:00 UTC is quiet in UTC but 21:00 in LA: also quiet; 23:00 UTC is 16:00 in LA: work day there only
    assert in_quiet_hours(prefs, "UTC", datetime(2026, 7, 1, 23, 0))
    assert not in_quiet_hours(prefs, "America/Los_Angeles", datetime(2026, 7, 1, 23, 0))


def test_next_work_start():
    prefs = UserPrefs()
    assert next_work_start(prefs, "America/Los_Angeles", datetime(2026, 3, 13, 2, 0)) == datetime(2026, 3, 13, 15, 0)
    # at the start instant itself the next one is a day later
    assert next_work_start(prefs, "UTC", datetime(2026, 3, 13, 8, 0)) == datetime(2026, 3, 14, 8, 0)


def test_default_recipients_rule():
    task = SimpleNamespace(owner_user_id="o", assigned_user_id="a")
    assert default_recipients(task, "close") == ["a"]
    assert default_recipients(task, "due") == ["a"]
    assert default_recipients(task, "past") == ["a", "o"]
    task.assigned_user_id = None
    assert default_recipients(task, "past") == ["o"]
    task.assigned_user_id = "o"
    assert default_recipients(task, "past") == ["o"]


def _task(due_at, remind=-3, due_time="09:30"):
    return SimpleNamespace(id="t", status="open", owner_user_id="u", assigned_user_id=None,
                           due_date=due_at.date(), due_time=due_time, due_at=due_at, remind_minutes_before=remind,
                           title="x", priority=None)


def test_past_zero_is_left_out_when_the_first_morning_comes_first():
    prefs = UserPrefs(time_zone="UTC", start_of_day=time(0, 0), end_of_day=time(17, 0))
    task = _task(datetime(2026, 3, 12, 23, 50))
    stages = stage_times(task, prefs, "UTC", datetime(2026, 3, 12))
    assert [(s.stage, s.seq) for s in stages][:3] == [("close", 0), ("due", 0), ("past", 1)]
    assert [s.at for s in stages] == sorted(s.at for s in stages)
    # and past 0 is never the current stage, at any minute
    clock = datetime(2026, 3, 12, 23, 50)
    seen = {current_stage(task, prefs, "UTC", clock + timedelta(minutes=m)) for m in range(120)}
    assert all(s is None or s.seq != 0 or s.stage != "past" for s in seen)


@pytest.mark.parametrize("due, start, scan_from", [
    (datetime(2026, 3, 6, 17, 0), time(2, 30), datetime(2026, 3, 7, 12, 0)),    # spring forward: 02:30 does not exist
    (datetime(2026, 10, 30, 16, 0), time(1, 30), datetime(2026, 10, 31, 12, 0)),  # fall back: 01:30 happens twice
])
def test_past_seq_is_decided_by_instants_around_daylight_saving(due, start, scan_from):
    prefs = UserPrefs(time_zone="America/New_York", start_of_day=start, end_of_day=time(22, 0))
    task = _task(due, remind=-2)
    listed = {(s.stage, s.seq): s.at for s in stage_times(task, prefs, "UTC", scan_from, past_days=30)}
    last_seq, flips = -1, {}
    for minute in range(3 * 24 * 60):
        now = scan_from + timedelta(minutes=minute)
        stage = current_stage(task, prefs, "UTC", now)
        seq = stage.seq if stage and stage.stage == "past" else last_seq
        assert seq >= last_seq, now  # never goes backwards
        if seq != last_seq:
            flips[seq] = now
        last_seq = seq
    for (name, seq), at in listed.items():
        if name == "past" and scan_from < at < scan_from + timedelta(days=3) and seq > 0:
            assert flips[seq] == at, (seq, flips[seq], at)  # flips exactly at the listed instant
            assert current_stage(task, prefs, "UTC", at - timedelta(minutes=1)).seq == seq - 1


def test_quiet_hours_truncate_to_the_minute():
    prefs = UserPrefs(start_of_day=time(8, 0), end_of_day=time(17, 0))
    assert not in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 17, 0, 30))
    assert not in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 17, 0, 59, 999))
    assert in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 17, 1, 0))
    assert not in_quiet_hours(prefs, "UTC", datetime(2026, 3, 12, 8, 0, 20))


def test_past_days_is_a_window_on_when_stages_start_not_a_cap_on_the_series():
    prefs = UserPrefs(time_zone="UTC")
    task = _task(datetime(2026, 3, 12, 12, 0))
    everything = stage_times(task, prefs, "UTC", datetime(2026, 3, 12))
    assert [(s.stage, s.seq) for s in everything][-1] == ("past", 5)
    later = datetime(2026, 3, 16, 12, 0)  # four days after the due instant
    window = stage_times(task, prefs, "UTC", later, past_days=2)
    assert window and all(s.at >= later - timedelta(days=2) for s in window)
    assert [(s.stage, s.seq) for s in window] == [("past", 3), ("past", 4), ("past", 5)]
    # a series longer than past_days is not truncated when its stages start inside the window
    long = stage_times(task, prefs, "UTC", datetime(2026, 3, 12), max_past=20, past_days=3)
    assert long[-1].seq == 20 and long[-1].last


def test_lead_of_exactly_the_cap_and_one_more():
    prefs = UserPrefs(time_zone="UTC")
    due = datetime(2026, 4, 1, 12, 0)
    at = {lead: stage_times(_task(due, remind=lead), prefs, "UTC", due)[0].at
          for lead in (MAX_LEAD_MINUTES - 1, MAX_LEAD_MINUTES, MAX_LEAD_MINUTES + 1)}
    assert MAX_LEAD_MINUTES == 10080
    assert due - at[10079] == timedelta(minutes=10079)
    assert due - at[10080] == timedelta(minutes=10080)
    assert at[10081] == at[10080]
