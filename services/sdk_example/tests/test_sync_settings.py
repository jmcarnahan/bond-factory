"""Settings over `/sync/upload`: table `task_user_settings`, the row id is the signed-in user's id."""

import pytest
from connections_util import headers

from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID
from sdk_example.models.task_settings import TaskUserSettings

TABLE = "task_user_settings"


def send(client, h, op, row_id, data, txn=1):
    body = {"transaction_id": txn, "ops": [{"seq": 0, "op": op, "table": TABLE, "id": row_id, "data": data}]}
    reply = client.post("/sync/upload", json=body, headers=h)
    assert reply.status_code == 200, reply.text
    return reply.json()["results"][0]


def stored(app, user):
    with app.state.session_factory() as session:
        row = session.get(TaskUserSettings, user)
        return None if row is None else (row.time_zone, row.start_of_day, row.end_of_day, row.lead_minutes)


def test_a_phone_writes_zone_and_end_of_day_and_a_date_only_task_follows(client, app):
    h = headers(client)
    task = client.post("/tasks", json={"title": "By evening", "due_date": "2026-11-09"}, headers=h).json()
    assert send(client, h, "put", DEMO_USER_ID, {"time_zone": "UTC", "end_of_day": "20:00"})["status"] == "ok"
    assert stored(app, DEMO_USER_ID) == ("UTC", None, "20:00", None)
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["due_at"] == "2026-11-09T20:00:00Z"
    assert client.get("/tasks/settings", headers=h).json()["end_of_day"] == "20:00"


def test_patch_means_the_same_and_null_resets(client, app):
    h = headers(client)
    send(client, h, "put", DEMO_USER_ID, {"time_zone": "UTC", "lead_minutes": 30})
    assert send(client, h, "patch", DEMO_USER_ID, {"end_of_day": "19:00"}, txn=2)["status"] == "ok"
    assert stored(app, DEMO_USER_ID) == ("UTC", None, "19:00", 30)
    send(client, h, "patch", DEMO_USER_ID, {"time_zone": None, "end_of_day": None}, txn=3)
    assert stored(app, DEMO_USER_ID) == (None, None, None, 30)


def test_another_users_row_is_refused_and_nothing_is_written(client, app):
    h = headers(client)
    result = send(client, h, "put", VIEWER_USER_ID, {"time_zone": "UTC"})
    assert (result["status"], result["code"], result["message"]) == ("rejected", "forbidden", "not_settings_owner")
    assert stored(app, VIEWER_USER_ID) is None and stored(app, DEMO_USER_ID) is None


@pytest.mark.parametrize("data,code", [
    ({"end_of_day": "25:00"}, "invalid_end_of_day"), ({"end_of_day": 800}, "invalid"),
    ({"time_zone": "Mars/Base"}, "invalid_time_zone"), ({"lead_minutes": -5}, "invalid_lead_minutes"),
    ({"lead_minutes": "soon"}, "invalid")])  # a value of the wrong storage type (800, "soon") is refused by the dispatcher's coercion, message "invalid"
def test_a_bad_value_is_a_verdict_not_a_500(client, app, data, code):
    h = headers(client)
    result = send(client, h, "put", DEMO_USER_ID, data)
    assert result["status"] == "rejected" and result["code"] == "invalid" and result["message"] == code, result
    assert stored(app, DEMO_USER_ID) is None


def test_a_delete_op_is_not_offered(client):
    h = headers(client)
    assert send(client, h, "delete", DEMO_USER_ID, {})["status"] == "rejected"


def test_a_work_day_change_over_sync_puts_away_the_notices_of_the_old_deadline(client, app):
    """The `moved` hook: a date-only task's deadline moves with the end of day, and the notice made for the old one goes."""
    from todo_util import inbox, sweep

    h = headers(client)
    send(client, h, "put", DEMO_USER_ID, {"time_zone": "UTC"})
    client.post("/tasks", json={"title": "By evening", "due_date": "2026-11-09"}, headers=h)
    sweep(client, h, "2026-11-09T16:20:00Z")  # the heads-up an hour before 17:00
    assert len(inbox(client, h)) == 1
    assert send(client, h, "patch", DEMO_USER_ID, {"end_of_day": "21:00"}, txn=2)["status"] == "ok"
    assert inbox(client, h) == []
