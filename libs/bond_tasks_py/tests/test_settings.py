from datetime import date, datetime, time

import pytest
from conftest import Task, UserSettings
from support_read import load_fixture, mk

from bond_tasks_py import SettingsUpdate, StoredPreferences, get_settings, update_settings
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.settings_schema import settings_item
from bond_tasks_py.timeutil import local_to_utc

NOW = datetime(2026, 3, 11, 20, 0)
LA = "America/Los_Angeles"


def update(session, user="u1", tz="UTC", **fields):
    return update_settings(session, settings_model=UserSettings, task_model=Task, user_id=user,
                           data=SettingsUpdate(**fields), tz=tz, now=NOW)


def test_defaults_when_no_row_and_no_row_created_by_reading(session):
    assert get_settings(session, UserSettings, "u1") == UserPrefs()
    assert StoredPreferences(UserSettings).for_user(session, "u1") == UserPrefs()
    assert session.get(UserSettings, "u1") is None


def test_update_creates_the_row_lazily_and_changes_only_sent_fields(session):
    prefs, warnings = update(session, time_zone=LA, lead_minutes=30)
    assert prefs == UserPrefs(time_zone=LA, start_of_day=time(8), end_of_day=time(17), lead_minutes=30)
    assert warnings == []
    prefs, _ = update(session, start_of_day="07:30")
    assert prefs == UserPrefs(time_zone=LA, start_of_day=time(7, 30), end_of_day=time(17), lead_minutes=30)
    assert StoredPreferences(UserSettings).for_user(session, "u1") == prefs
    assert session.get(UserSettings, "u1").updated_at == NOW
    assert get_settings(session, UserSettings, "u2") == UserPrefs()  # another user is untouched


def test_unknown_zone_is_refused_and_writes_nothing(session):
    with pytest.raises(TaskError) as err:
        update(session, time_zone="Mars/Olympus")
    assert err.value.code == "invalid_time_zone" and err.value.status == 422
    assert session.get(UserSettings, "u1") is None


def test_clearing_the_zone_with_null_is_allowed(session):
    update(session, time_zone=LA)
    prefs, _ = update(session, time_zone=None)
    assert prefs.time_zone is None


def test_equal_start_and_end_is_refused(session):
    with pytest.raises(TaskError) as err:
        update(session, start_of_day="09:00", end_of_day="09:00")
    assert err.value.code == "invalid_work_day" and err.value.status == 422
    update(session, end_of_day="20:00")
    with pytest.raises(TaskError):  # equal to the STORED other end, not only to a sent one
        update(session, start_of_day="20:00")
    assert get_settings(session, UserSettings, "u1").end_of_day == time(20)


def test_work_day_across_midnight_is_accepted(session):
    prefs, warnings = update(session, time_zone=LA, start_of_day="20:00", end_of_day="04:00", lead_minutes=60)
    assert (prefs.start_of_day, prefs.end_of_day) == (time(20), time(4)) and warnings == []


def test_lead_longer_than_the_work_day_warns_but_saves(session):
    prefs, warnings = update(session, time_zone=LA, start_of_day="09:00", end_of_day="10:00", lead_minutes=120)
    assert warnings == ["lead_longer_than_work_day"] and prefs.lead_minutes == 120
    assert get_settings(session, UserSettings, "u1").lead_minutes == 120
    _, warnings = update(session, end_of_day="11:00")  # a 120 minute work day equals the lead: no warning
    assert warnings == []


def test_end_of_day_change_moves_date_only_instants_not_timed_ones(session):
    day = date(2026, 3, 20)
    update(session, time_zone=LA)
    mk(session, Task, "dated", due=day, due_at=local_to_utc(day, time(17), LA))
    timed = mk(session, Task, "timed", due=day, due_time="10:00", due_at=local_to_utc(day, time(10), LA))
    mk(session, Task, "theirs", owner="u2", due=day, due_at=local_to_utc(day, time(17), LA))
    done = mk(session, Task, "done", due=day, due_at=local_to_utc(day, time(17), LA), status="done")
    update(session, end_of_day="18:30")
    assert session.get(Task, "dated").due_at == local_to_utc(day, time(18, 30), LA)
    assert timed.due_at == local_to_utc(day, time(10), LA)
    assert session.get(Task, "theirs").due_at == local_to_utc(day, time(17), LA)
    assert done.due_at == local_to_utc(day, time(17), LA)


def test_zone_change_moves_date_only_instants(session):
    day = date(2026, 3, 20)
    update(session, time_zone=LA)
    mk(session, Task, "dated", due=day, due_at=local_to_utc(day, time(17), LA))
    update(session, time_zone="America/New_York")
    assert session.get(Task, "dated").due_at == local_to_utc(day, time(17), "America/New_York")


def test_lead_change_alone_recomputes_nothing(session):
    day = date(2026, 3, 20)
    update(session, time_zone=LA)
    mk(session, Task, "dated", due=day, due_at=datetime(2026, 1, 1))  # a marker value recompute would replace
    update(session, lead_minutes=15)
    assert session.get(Task, "dated").due_at == datetime(2026, 1, 1)


def test_resending_the_stored_end_of_day_and_zone_recomputes_nothing(session):
    day = date(2026, 3, 20)
    update(session, time_zone=LA, end_of_day="17:00")
    marker = datetime(2026, 1, 1)
    mk(session, Task, "dated", due=day, due_at=marker)
    update(session, time_zone=LA, end_of_day="17:00")  # same values as stored
    assert session.get(Task, "dated").due_at == marker
    update(session, end_of_day="18:00")  # a real change recomputes
    assert session.get(Task, "dated").due_at == local_to_utc(day, time(18), LA)


def test_work_day_change_without_a_stored_zone_warns_but_saves(session):
    day = date(2026, 3, 20)
    mk(session, Task, "dated", due=day, due_at=local_to_utc(day, time(17), LA))  # made with a zone sent at write time
    prefs, warnings = update(session, end_of_day="18:00")
    assert warnings == ["time_zone_unknown"] and prefs.end_of_day == time(18) and prefs.time_zone is None
    assert session.get(Task, "dated").due_at == local_to_utc(day, time(18), "UTC")  # the app default (tz="UTC")
    _, warnings = update(session, lead_minutes=30)  # the work day did not change
    assert warnings == []
    _, warnings = update(session, time_zone=LA, end_of_day="19:00")  # a zone is now stored
    assert warnings == []
    _, warnings = update(session, start_of_day="07:00")  # start_of_day alone, zone stored
    assert warnings == []


def test_start_of_day_change_without_a_stored_zone_also_warns(session):
    _, warnings = update(session, start_of_day="07:00")
    assert warnings == ["time_zone_unknown"]


def test_wire_item_matches_the_fixture(session):
    prefs, warnings = update(session, time_zone=LA)
    assert settings_item(prefs, warnings) == load_fixture("settings.json")
    assert settings_item(UserPrefs(), ["lead_longer_than_work_day"]) == {
        "time_zone": None, "start_of_day": "08:00", "end_of_day": "17:00", "lead_minutes": 60,
        "warnings": ["lead_longer_than_work_day"]}
