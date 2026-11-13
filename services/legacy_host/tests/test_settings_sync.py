"""Settings over `/sync/upload` for an app whose preferences table pre-dates the modules (`user_prefs`, renamed columns)."""

import pytest
from conftest import as_user
from fastapi.testclient import TestClient
from legacy_db import legacy_app
from sqlalchemy import text
from sync_util import upload


def send(client, user, op, row, data, seq=0):
    body = {"transaction_id": 1, "ops": [{"seq": seq, "op": op, "table": "user_prefs", "id": row, "data": data}]}
    reply = upload(client, user, body)
    assert reply.status_code == 200, reply.text
    return reply.json()["results"][0]


def prefs(app, uid):
    with app.state.engine.connect() as conn:
        row = conn.execute(text("SELECT tz, day_start, day_end, remind_lead, theme FROM user_prefs WHERE uid = :u"),
                           {"u": uid}).first()
    return None if row is None else tuple(row)


def date_only_task(client, task_id="t-d"):
    r = client.post("/tasks", json={"id": task_id, "title": "By evening", "due_date": "2026-11-20"},
                    headers=as_user("u-owner"))
    assert r.status_code in (200, 201), r.text
    return task_id


def due_at(app, task_id):
    with app.state.engine.connect() as conn:
        return conn.execute(text("SELECT due_at FROM tasks WHERE id = :i"), {"i": task_id}).scalar()


def test_legacy_keys_write_the_renamed_columns_and_move_a_date_only_instant(app, client):
    task = date_only_task(client)
    before = due_at(app, task)
    result = send(client, "u-owner", "put", "u-owner", {"tz": "America/Chicago", "day_end": "18:30"})
    assert result == {"seq": 0, "status": "ok"}
    assert prefs(app, "u-owner") == ("America/Chicago", None, "18:30", None, None)
    assert due_at(app, task) != before  # recomputed in the same transaction (zone and end of day)


def test_the_libs_keys_work_too_and_a_lib_key_wins(client, app):
    assert send(client, "u-owner", "patch", "u-owner", {"time_zone": "UTC", "tz": "America/Chicago",
                                                         "end_of_day": "19:00", "lead_minutes": 20})["status"] == "ok"
    assert prefs(app, "u-owner") == ("UTC", None, "19:00", 20, None)


def test_a_null_resets_and_an_absent_key_is_unchanged(client, app):
    send(client, "u-owner", "put", "u-owner", {"tz": "UTC", "day_start": "07:00", "remind_lead": 30})
    send(client, "u-owner", "patch", "u-owner", {"day_start": None})
    assert prefs(app, "u-owner") == ("UTC", None, None, 30, None)


def test_a_second_users_row_is_refused_and_nothing_is_written(client, app):
    result = send(client, "u-owner", "put", "u-editor", {"tz": "UTC"})
    assert (result["status"], result["code"], result["message"]) == ("rejected", "forbidden", "not_settings_owner")
    assert prefs(app, "u-editor") is None and prefs(app, "u-owner") is None


@pytest.mark.parametrize("data,message", [({"day_end": "25:00"}, "invalid_end_of_day"),
                                          ({"day_start": "8"}, "invalid_start_of_day"),
                                          ({"tz": "Mars/Base"}, "invalid_time_zone"),
                                          ({"remind_lead": -3}, "invalid_lead_minutes")])
def test_a_bad_value_is_a_verdict_and_writes_nothing(client, app, data, message):
    result = send(client, "u-owner", "put", "u-owner", data)
    assert (result["status"], result["code"], result["message"]) == ("rejected", "invalid", message)
    assert prefs(app, "u-owner") is None


@pytest.mark.parametrize("lead", [True, False, 30.5])
def test_a_bool_or_fractional_lead_is_invalid_and_the_row_untouched(client, app, lead):
    send(client, "u-owner", "put", "u-owner", {"tz": "UTC"})
    result = send(client, "u-owner", "patch", "u-owner", {"lead_minutes": lead})
    assert (result["status"], result["code"], result["message"]) == ("rejected", "invalid", "invalid_lead_minutes")
    assert prefs(app, "u-owner") == ("UTC", None, None, None, None)


def test_the_app_column_theme_is_left_alone(tmp_path):
    def fill(connection):
        connection.execute(text("INSERT INTO user_prefs (uid, theme, updated_at) VALUES ('u-owner', 'dark', "
                                "'2026-11-01 09:00:00')"))

    app = legacy_app(tmp_path / "theme.db", fill)
    client = TestClient(app)
    assert send(client, "u-owner", "patch", "u-owner", {"tz": "UTC", "theme": "light", "user_id": "u-editor"})["status"] == "ok"
    assert prefs(app, "u-owner") == ("UTC", None, None, None, "dark") and prefs(app, "u-editor") is None


def test_a_row_that_pre_dates_adoption_is_updated_in_place(tmp_path):
    def fill(connection):
        connection.execute(text("INSERT INTO user_prefs (uid, tz, day_start, day_end, remind_lead, theme, updated_at) "
                                "VALUES ('u-owner', 'America/Chicago', '07:30', NULL, 45, 'dark', '2026-11-01 09:00:00')"))

    app = legacy_app(tmp_path / "old.db", fill)
    assert send(TestClient(app), "u-owner", "put", "u-owner", {"day_end": "19:00"})["status"] == "ok"
    assert prefs(app, "u-owner") == ("America/Chicago", "07:30", "19:00", 45, "dark")


def test_a_legacy_row_holding_seconds_is_an_invalid_verdict_today(tmp_path):
    """LIMIT (recorded): an old `day_start` of '08:00:00' cannot be read by the lib, so a settings write for that user is
    refused `invalid` and nothing changes; normalise such rows in the adoption migration (the REST read fails the same)."""
    def fill(connection):
        connection.execute(text("INSERT INTO user_prefs (uid, day_start, updated_at) VALUES ('u-owner', '08:00:00', "
                                "'2026-11-01 09:00:00')"))

    app = legacy_app(tmp_path / "secs.db", fill)
    result = send(TestClient(app), "u-owner", "put", "u-owner", {"tz": "UTC"})
    assert result["status"] == "rejected" and result["code"] == "invalid"
    assert prefs(app, "u-owner") == (None, "08:00:00", None, None, None)


def test_a_delete_op_is_not_offered(client):
    assert send(client, "u-owner", "delete", "u-owner", {})["status"] == "rejected"
