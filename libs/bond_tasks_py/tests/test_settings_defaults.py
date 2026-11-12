"""App-set defaults for the work day: NULL columns, ``overridden``, reset by null."""

from datetime import date, datetime, time

from conftest import Task, UserSettings
from support_read import mk

from bond_tasks_py import (
    SettingsUpdate,
    StoredPreferences,
    get_settings,
    settings_item,
    settings_overridden,
    update_settings,
)
from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.timeutil import local_to_utc

NOW = datetime(2026, 3, 11, 20, 0)
LA = "America/Los_Angeles"
APP = UserPrefs(time_zone="America/Chicago", start_of_day=time(9), end_of_day=time(16), lead_minutes=30)


def update(session, defaults=None, tz="UTC", **fields):
    return update_settings(session, settings_model=UserSettings, task_model=Task, user_id="u1",
                           data=SettingsUpdate(**fields), tz=tz, now=NOW, defaults=defaults)


def test_missing_row_uses_app_defaults(session):
    assert get_settings(session, UserSettings, "u1", APP) == APP
    assert StoredPreferences(UserSettings, APP).for_user(session, "u1") == APP
    assert settings_overridden(session.get(UserSettings, "u1")) == []
    assert session.get(UserSettings, "u1") is None


def test_unset_fields_of_a_row_take_the_app_default(session):
    update(session, APP, lead_minutes=15)
    assert get_settings(session, UserSettings, "u1", APP) == UserPrefs(
        time_zone="America/Chicago", start_of_day=time(9), end_of_day=time(16), lead_minutes=15)
    row = session.get(UserSettings, "u1")
    assert (row.time_zone, row.start_of_day, row.end_of_day, row.lead_minutes) == (None, None, None, 15)


def test_none_defaults_are_todays_constants(session):
    assert get_settings(session, UserSettings, "u1", None) == UserPrefs()
    update(session, lead_minutes=45)
    assert get_settings(session, UserSettings, "u1") == UserPrefs(lead_minutes=45)
    assert StoredPreferences(UserSettings).for_user(session, "u1").end_of_day == time(17)


def test_null_field_resets_to_default(session):
    update(session, APP, time_zone=LA, start_of_day="07:00", end_of_day="18:00", lead_minutes=5)
    prefs, _ = update(session, APP, start_of_day=None, lead_minutes=None)
    assert (prefs.start_of_day, prefs.lead_minutes) == (time(9), 30)
    assert (prefs.time_zone, prefs.end_of_day) == (LA, time(18))
    row = session.get(UserSettings, "u1")
    assert row.start_of_day is None and row.lead_minutes is None and row.end_of_day == "18:00"
    prefs, _ = update(session, APP, time_zone=None)  # absent fields stay, null resets the zone
    assert prefs.time_zone == "America/Chicago" and prefs.end_of_day == time(18)


def test_overridden_lists_only_user_set_fields(session):
    update(session, APP, lead_minutes=20, time_zone=LA)
    assert settings_overridden(session.get(UserSettings, "u1")) == ["time_zone", "lead_minutes"]
    update(session, APP, end_of_day="18:00", time_zone=None)
    assert settings_overridden(session.get(UserSettings, "u1")) == ["end_of_day", "lead_minutes"]
    prefs = get_settings(session, UserSettings, "u1", APP)
    item = settings_item(prefs, [], settings_overridden(session.get(UserSettings, "u1")))
    assert item["overridden"] == ["end_of_day", "lead_minutes"] and item["end_of_day"] == "18:00"
    assert "overridden" not in settings_item(prefs)


def test_recompute_runs_when_default_end_of_day_applies(session):
    day = date(2026, 3, 20)
    update(session, APP, time_zone=LA, end_of_day="18:00")
    mk(session, Task, "dated", due=day, due_at=local_to_utc(day, time(18), LA))
    update(session, APP, end_of_day=None)  # the effective end of day is now the app's 16:00
    assert session.get(Task, "dated").due_at == local_to_utc(day, time(16), LA)


def test_recompute_runs_when_default_zone_applies(session):
    day = date(2026, 3, 20)
    update(session, APP, time_zone=LA)
    mk(session, Task, "dated", due=day, due_at=local_to_utc(day, time(16), LA))
    update(session, APP, time_zone=None)
    assert session.get(Task, "dated").due_at == local_to_utc(day, time(16), "America/Chicago")


def test_equal_effective_times_are_refused_when_one_is_a_default(session):
    import pytest

    from bond_tasks_py import TaskError
    with pytest.raises(TaskError) as err:
        update(session, APP, start_of_day="16:00")  # the default end of day is 16:00
    assert err.value.code == "invalid_work_day"
