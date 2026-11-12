"""App-set work-day defaults (NULL = follow the app default), the 0006 migration, and the sweep's grandfather cutoff."""

from datetime import datetime
from pathlib import Path

import pytest
from alembic.config import Config
from connections_util import headers
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from tasks_util import code
from todo_util import notices_of, sweep, timed

from alembic import command
from sdk_example.main import create_app
from sdk_example.models.auth import DEMO_USER_ID
from sdk_example.models.task_settings import TaskUserSettings
from sdk_example.settings import Settings

SERVICE = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path, monkeypatch, clean_env):
    """A fake-mode app whose default work day is 07:30 to 18:00 with a 30 minute lead."""
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("SDK_EXAMPLE_START_OF_DAY", "07:30")
    monkeypatch.setenv("SDK_EXAMPLE_END_OF_DAY", "18:00")
    monkeypatch.setenv("SDK_EXAMPLE_LEAD_MINUTES", "30")
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, headers={"Origin": "http://localhost:8078"})


@pytest.fixture
def h(client):
    return headers(client)


APP_DEFAULT = {"time_zone": None, "start_of_day": "07:30", "end_of_day": "18:00", "lead_minutes": 30, "warnings": [],
               "overridden": []}


def test_a_person_with_nothing_stored_gets_the_app_default_and_nothing_is_overridden(client, h):
    assert client.get("/tasks/settings", headers=h).json() == APP_DEFAULT


def test_every_preferences_object_carries_the_same_default(app):
    state = app.state
    assert (state.default_prefs.start_of_day.strftime("%H:%M"), state.default_prefs.end_of_day.strftime("%H:%M"),
            state.default_prefs.lead_minutes) == ("07:30", "18:00", 30)
    assert state.todo_prefs.defaults is state.default_prefs
    with state.session_factory() as session:
        assert state.todo_prefs.for_user(session, "nobody") == state.default_prefs


def test_a_stored_field_overrides_and_null_resets_it(client, h):
    body = client.put("/tasks/settings", json={"end_of_day": "19:00", "time_zone": "UTC"}, headers=h).json()
    assert (body["end_of_day"], body["start_of_day"], body["overridden"]) == ("19:00", "07:30", ["time_zone", "end_of_day"])
    back = client.put("/tasks/settings", json={"end_of_day": None}, headers=h).json()
    assert (back["end_of_day"], back["overridden"]) == ("18:00", ["time_zone"])
    assert client.get("/tasks/settings", headers=h).json()["overridden"] == ["time_zone"]
    nothing = client.put("/tasks/settings", json={"time_zone": None}, headers=h).json()
    assert nothing == {**APP_DEFAULT, "warnings": nothing["warnings"]}


def test_a_reset_that_changes_the_effective_end_of_day_moves_a_date_only_deadline(client, h):
    client.put("/tasks/settings", json={"time_zone": "UTC", "end_of_day": "20:00"}, headers=h)
    task = client.post("/tasks", json={"title": "By evening", "due_date": "2026-11-09"}, headers=h).json()
    assert task["due_at"] == "2026-11-09T20:00:00Z"
    client.put("/tasks/settings", json={"end_of_day": None}, headers=h)
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["due_at"] == "2026-11-09T18:00:00Z"


def test_a_new_date_only_task_uses_the_app_default_end_of_day(client, h):
    client.put("/tasks/settings", json={"time_zone": "UTC"}, headers=h)
    task = client.post("/tasks", json={"title": "Plain", "due_date": "2026-11-09"}, headers=h).json()
    assert task["due_at"] == "2026-11-09T18:00:00Z"


def test_equal_start_and_end_after_a_reset_is_still_refused(client, h):
    client.put("/tasks/settings", json={"start_of_day": "18:00"}, headers=h)
    refused = client.put("/tasks/settings", json={"start_of_day": "18:00", "end_of_day": None}, headers=h)
    assert refused.status_code == 422 and code(refused) == "invalid_work_day"


def test_the_defaults_come_from_the_environment_and_a_bad_value_stops_startup(monkeypatch, clean_env):
    assert Settings.from_env().start_of_day == "08:00"
    monkeypatch.setenv("SDK_EXAMPLE_START_OF_DAY", "07:30")
    assert Settings.from_env().start_of_day == "07:30"
    monkeypatch.setenv("SDK_EXAMPLE_END_OF_DAY", "6pm")
    with pytest.raises(RuntimeError, match="HH:MM"):
        Settings.from_env()
    monkeypatch.setenv("SDK_EXAMPLE_END_OF_DAY", "18:00")
    monkeypatch.setenv("SDK_EXAMPLE_LEAD_MINUTES", "-5")
    with pytest.raises(RuntimeError, match="LEAD_MINUTES"):
        Settings.from_env()


def test_today_default_is_08_00_17_00_60_when_nothing_is_set(tmp_path, monkeypatch, clean_env):
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/plain.db")
    plain = TestClient(create_app(), headers={"Origin": "http://localhost:8078"})
    assert plain.get("/tasks/settings", headers=headers(plain)).json() == {
        "time_zone": None, "start_of_day": "08:00", "end_of_day": "17:00", "lead_minutes": 60, "warnings": [],
        "overridden": []}


# --- migration 0006 ----------------------------------------------------------------------------------------------


def columns(url: str) -> dict[str, bool]:
    return {c["name"]: c["nullable"] for c in inspect(create_engine(url)).get_columns("task_user_settings")}


def test_0006_makes_the_work_day_nullable_and_the_downgrade_fills_and_restores_not_null(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/m.db"
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", url)
    config = Config()
    config.set_main_option("script_location", str(SERVICE / "alembic"))
    command.upgrade(config, "head")
    assert columns(url) == {"user_id": False, "time_zone": True, "start_of_day": True, "end_of_day": True,
                            "lead_minutes": True, "updated_at": False}
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO task_user_settings (user_id, updated_at) VALUES ('u-null', '2026-11-08 10:00:00')"))
        conn.execute(text("INSERT INTO task_user_settings (user_id, end_of_day, updated_at) "
                          "VALUES ('u-set', '19:30', '2026-11-08 10:00:00')"))
    command.downgrade(config, "0005")
    after = columns(url)
    assert (after["start_of_day"], after["end_of_day"], after["lead_minutes"]) == (False, False, False)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT user_id, start_of_day, end_of_day, lead_minutes FROM task_user_settings "
                                 "ORDER BY user_id")).all()
    assert [tuple(r) for r in rows] == [("u-null", "08:00", "17:00", 60), ("u-set", "08:00", "19:30", 60)]
    command.upgrade(config, "head")
    assert columns(url)["end_of_day"] is True
    with engine.connect() as conn:  # values equal to the old constants go back to NULL (follow the default); 19:30 stays
        rows = conn.execute(text("SELECT user_id, start_of_day, end_of_day, lead_minutes FROM task_user_settings "
                                 "ORDER BY user_id")).all()
    assert [tuple(r) for r in rows] == [("u-null", None, None, None), ("u-set", None, "19:30", None)]


def test_the_model_stores_null_for_an_unset_field(client, app, h):
    client.put("/tasks/settings", json={"lead_minutes": 5}, headers=h)
    with app.state.session_factory() as session:
        row = session.get(TaskUserSettings, DEMO_USER_ID)
        assert (row.start_of_day, row.end_of_day, row.lead_minutes) == (None, None, 5)


# --- the sweep's grandfather cutoff ------------------------------------------------------------------------------


def test_a_task_due_before_the_cutoff_sends_nothing_on_any_later_morning(client, app, h):
    old = timed(client, h, title="Old", day="2026-11-09", at="10:00")
    new = timed(client, h, title="New", day="2026-11-10", at="10:00")
    object.__setattr__(app.state.settings, "grandfather_before", datetime(2026, 11, 10))  # the activation time
    sweep(client, h, "2026-11-09T10:05:00Z")
    sweep(client, h, "2026-11-10T10:05:00Z")
    assert notices_of(app, old["id"]) == []
    assert [n.data["stage"] for n in notices_of(app, new["id"])] == ["due"]


def test_without_a_cutoff_the_old_task_notifies(client, app, h):
    old = timed(client, h, title="Old", day="2026-11-09", at="10:00")
    sweep(client, h, "2026-11-09T10:05:00Z")
    assert [n.data["stage"] for n in notices_of(app, old["id"])] == ["due"]


def test_the_cutoff_is_read_from_the_environment(monkeypatch, clean_env):
    assert Settings.from_env().grandfather_before is None
    monkeypatch.setenv("SDK_EXAMPLE_GRANDFATHER_BEFORE", "2026-11-10T00:00:00Z")
    assert Settings.from_env().grandfather_before.isoformat() == "2026-11-10T00:00:00"
    monkeypatch.setenv("SDK_EXAMPLE_GRANDFATHER_BEFORE", "yesterday")
    with pytest.raises(RuntimeError, match="ISO 8601"):
        Settings.from_env()

