"""Settings over sync: the route of the settings table, put and patch alike, own row only."""

from dataclasses import dataclass
from datetime import date, datetime, time

import pytest
from conftest import Task, UserSettings
from support_read import mk

from bond_tasks_py import settings_routes, settings_verdict_for
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.settings_routes import SETTINGS_FIELDS
from bond_tasks_py.timeutil import local_to_utc

NOW = datetime(2026, 3, 11, 20, 0)
LA = "America/Los_Angeles"
DAY = date(2026, 3, 20)


@dataclass
class Op:
    id: str
    op: str = "put"


@dataclass
class Ctx:
    user: object
    background: object = None


def route(**kw):
    return settings_routes(UserSettings, Task, now=lambda: NOW, **kw)[("task_user_settings", None)]


def send(session, data, *, op="put", row="u1", user="u1", **kw):
    return route(**kw).handler(session, Ctx(user), Op(row, op), data)


def stored(session, user="u1"):
    row = session.get(UserSettings, user)
    return None if row is None else tuple(getattr(row, f) for f in SETTINGS_FIELDS)


def test_the_route_key_ops_and_reads():
    table = settings_routes(UserSettings, Task)
    assert list(table) == [("task_user_settings", None)]
    r = table[("task_user_settings", None)]
    assert r.ops == frozenset({"put", "patch"}) and r.reads == SETTINGS_FIELDS  # no delete op


@pytest.mark.parametrize("op", ["put", "patch"])
def test_time_zone_and_end_of_day_are_stored_and_the_date_only_instant_follows(session, op):
    mk(session, Task, "dated", due=DAY, due_at=local_to_utc(DAY, time(17), "UTC"))
    send(session, {"time_zone": LA, "end_of_day": "18:30"}, op=op)
    assert stored(session) == (LA, None, "18:30", None)
    assert session.get(Task, "dated").due_at == local_to_utc(DAY, time(18, 30), LA)  # same transaction
    assert session.get(UserSettings, "u1").updated_at == NOW


def test_absent_key_is_unchanged_and_null_resets(session):
    send(session, {"time_zone": LA, "start_of_day": "07:00", "lead_minutes": 30})
    send(session, {"lead_minutes": 45}, op="patch")
    assert stored(session) == (LA, "07:00", None, 45)
    send(session, {"time_zone": None, "start_of_day": None})
    assert stored(session) == (None, None, None, 45)


def test_reset_returns_to_the_app_default_with_and_without_defaults(session):
    app_default = UserPrefs(time_zone="Europe/Paris", start_of_day=time(9), end_of_day=time(18), lead_minutes=15)
    send(session, {"end_of_day": "20:00"}, defaults=app_default)
    send(session, {"end_of_day": None}, defaults=app_default)
    assert stored(session)[2] is None
    from bond_tasks_py import get_settings
    assert get_settings(session, UserSettings, "u1", app_default).end_of_day == time(18)
    assert get_settings(session, UserSettings, "u1").end_of_day == time(17)


def test_another_users_row_is_forbidden_and_writes_nothing(session):
    with pytest.raises(TaskError) as caught:
        send(session, {"time_zone": LA}, row="u2")
    assert settings_verdict_for(caught.value) == ("forbidden", "not_settings_owner")
    assert stored(session, "u2") is None and stored(session) is None


def test_the_payload_never_names_the_user_and_unknown_keys_are_ignored(session):
    send(session, {"time_zone": LA, "user_id": "u2", "theme": "dark", "updated_at": "x"})
    assert stored(session) == (LA, None, None, None) and stored(session, "u2") is None


def test_ctx_user_may_be_an_object(session):
    @dataclass
    class User:
        user_id: str

    route().handler(session, Ctx(User("u1")), Op("u1"), {"lead_minutes": 5})
    assert stored(session)[3] == 5


@pytest.mark.parametrize("data,code", [
    ({"start_of_day": "25:00"}, "invalid_start_of_day"), ({"end_of_day": "8"}, "invalid_end_of_day"),
    ({"end_of_day": 800}, "invalid_end_of_day"), ({"time_zone": "Mars/Base"}, "invalid_time_zone"),
    ({"time_zone": 5}, "invalid_time_zone"), ({"lead_minutes": -1}, "invalid_lead_minutes"),
    ({"lead_minutes": "soon"}, "invalid_lead_minutes"), ({"lead_minutes": 99999}, "invalid_lead_minutes"),
    ({"start_of_day": "09:00", "end_of_day": "09:00"}, "invalid_work_day"),
])
@pytest.mark.parametrize("op", ["put", "patch"])
def test_a_bad_value_is_an_invalid_verdict_with_the_code_and_writes_nothing(session, data, code, op):
    with pytest.raises(TaskError) as caught:  # the one error settings_verdict_for maps
        send(session, data, op=op)
    assert settings_verdict_for(caught.value) == ("invalid", code)
    assert stored(session) is None


def test_the_verdict_mapper_ignores_other_errors():
    assert settings_verdict_for(ValueError("x")) is None


def test_on_recomputed_is_called_with_the_session_for_each_moved_task(session):
    mk(session, Task, "dated", due=DAY, due_at=local_to_utc(DAY, time(17), "UTC"))
    seen = []
    send(session, {"end_of_day": "19:00"}, on_recomputed=lambda s, task, old, moment: seen.append((s, task.id, moment)))
    assert seen == [(session, "dated", NOW)]


@pytest.mark.parametrize("lead", [True, False, 30.5])
@pytest.mark.parametrize("op", ["put", "patch"])
def test_a_bool_or_fractional_lead_is_invalid(session, lead, op):
    with pytest.raises(TaskError) as caught:
        send(session, {"lead_minutes": lead}, op=op)
    assert settings_verdict_for(caught.value) == ("invalid", "invalid_lead_minutes") and stored(session) is None


def test_a_whole_float_lead_is_taken(session):
    send(session, {"lead_minutes": 30.0})
    assert stored(session)[3] == 30


class Blind:
    """A session proxy whose first `get` of the settings row misses: the other writer had not committed yet."""

    def __init__(self, session, misses):
        self._s, self.misses = session, misses  # `misses` is a shared one-item list

    def get(self, model, key):
        if model is UserSettings and self.misses[0]:
            self.misses[0] -= 1
            return None
        return self._s.get(model, key)

    def __getattr__(self, name):
        return getattr(self._s, name)


def race(monkeypatch, misses):
    from bond_tasks_py import usersettings
    real, left = usersettings.update_settings, [misses]
    monkeypatch.setattr(usersettings, "update_settings", lambda session, **kw: real(Blind(session, left), **kw))


def test_a_lost_first_put_race_retries_once_and_updates_the_winners_row(session, monkeypatch):
    session.add(UserSettings(user_id="u1", lead_minutes=10, updated_at=NOW))
    session.flush()  # the winner's row
    race(monkeypatch, 1)  # this pass did not see it, so it inserts and fails
    send(session, {"end_of_day": "19:00"})
    assert stored(session) == (None, None, "19:00", 10)  # updated in place: the winner's lead kept


def test_a_second_failure_is_a_conflict_verdict(session, monkeypatch):
    session.add(UserSettings(user_id="u1", lead_minutes=10, updated_at=NOW))
    session.flush()
    race(monkeypatch, 2)
    with pytest.raises(TaskError) as caught:
        send(session, {"end_of_day": "19:00"})
    assert settings_verdict_for(caught.value) == ("conflict", "settings_conflict")
