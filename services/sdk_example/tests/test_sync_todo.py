"""Notices and push devices on the sync host, and the inbox staying in step with task changes made over sync."""

from datetime import UTC, datetime

import pytest
from bond_push_py import device_row_id
from bond_sync_py import Ctx, UploadRequest, upload
from connections_util import headers
from todo_util import inbox, notices_of, sweep, timed

from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID
from sdk_example.models.push import PushDevice
from sdk_example.routes.sync import build_host


@pytest.fixture
def h(client):
    return headers(client)


def op(seq, kind, table, id_, data=None, action=None):
    return {"seq": seq, "op": kind, "table": table, "id": id_, "action": action, "data": data or {}}


def send(app, user, *ops):
    body = UploadRequest.model_validate({"transaction_id": 1, "ops": list(ops)})
    return upload(app.state.session_factory, build_host(app), Ctx(user=user), body).wire()["results"]


def verdicts(results):
    return [(r["status"], r.get("code"), r.get("message")) for r in results]


def test_a_device_reads_and_dismisses_its_own_notice(client, app, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    [notice] = inbox(client, h)
    app.state.clock.freeze(datetime(2026, 11, 9, 9, 45, tzinfo=UTC))
    results = send(app, DEMO_USER_ID, op(0, "patch", "notices", notice["id"], {"read_at": "2020-01-01T00:00:00Z"}))
    assert verdicts(results) == [("ok", None, None)]
    stored = notices_of(app, task["id"])[0]
    assert stored.read_at == datetime(2026, 11, 9, 9, 45)  # the server's clock, never the device's
    send(app, DEMO_USER_ID, op(1, "patch", "notices", notice["id"], {"dismissed_at": "2020-01-01T00:00:00Z"}))
    assert inbox(client, h) == []


def test_a_device_cannot_touch_another_users_notice_or_write_server_columns(client, app, h):
    timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    [notice] = inbox(client, h)
    stolen = send(app, VIEWER_USER_ID, op(0, "patch", "notices", notice["id"], {"read_at": "2026-11-09T09:31:00Z"}))
    assert verdicts(stolen) == [("rejected", "forbidden", "not_notice_owner")]
    forged = send(app, DEMO_USER_ID, op(1, "put", "notices", "x" * 32, {"title": "hello", "body": "b"}))
    assert forged[0]["status"] == "rejected"
    assert notices_of(app, notice["data"]["task_id"])[0].read_at is None
    send(app, DEMO_USER_ID, op(2, "patch", "notices", notice["id"], {"title": "Renamed", "read_at": "2026-11-09T09:32:00Z"}))
    assert inbox(client, h)[0]["title"] != "Renamed"


def test_a_device_registers_its_own_row_and_user_id_comes_from_the_session(client, app):
    row_id = device_row_id(DEMO_USER_ID, "dev-7")
    data = {"device_id": "dev-7", "token": "tok-7", "platform": "ios", "environment": "sandbox",
            "user_id": "someone-else"}
    assert verdicts(send(app, DEMO_USER_ID, op(0, "put", "push_devices", row_id, data))) == [("ok", None, None)]
    with app.state.session_factory() as session:
        row = session.get(PushDevice, row_id)
        assert (row.user_id, row.token) == (DEMO_USER_ID, "tok-7")
    patched = send(app, DEMO_USER_ID, op(1, "patch", "push_devices", row_id, {"token": "tok-8"}))
    assert verdicts(patched) == [("ok", None, None)]


def test_a_device_cannot_change_or_delete_another_users_device_row(client, app):
    row_id = device_row_id(DEMO_USER_ID, "dev-7")
    send(app, DEMO_USER_ID, op(0, "put", "push_devices", row_id,
                               {"device_id": "dev-7", "token": "tok-7", "platform": "ios", "environment": "sandbox"}))
    attempts = send(app, VIEWER_USER_ID, op(1, "patch", "push_devices", row_id, {"token": "tok-evil"}),
                    op(2, "delete", "push_devices", row_id))
    with app.state.session_factory() as session:
        row = session.get(PushDevice, row_id)
        assert row is not None and row.token == "tok-7"
    assert attempts[0]["status"] == "rejected"


def test_completing_a_task_over_sync_puts_its_notices_away(client, app, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    assert len(inbox(client, h)) == 1
    done = send(app, DEMO_USER_ID, op(0, "patch", "tasks", task["id"], action="complete"))
    assert verdicts(done) == [("ok", None, None)]
    assert inbox(client, h) == []


def test_deleting_a_task_over_sync_puts_its_notices_away(client, app, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    assert verdicts(send(app, DEMO_USER_ID, op(0, "delete", "tasks", task["id"]))) == [("ok", None, None)]
    assert inbox(client, h) == []


def test_moving_a_task_over_sync_puts_the_old_notices_away(client, app, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    send(app, DEMO_USER_ID, op(0, "patch", "tasks", task["id"], {"due_time": "15:00"}))
    assert inbox(client, h) == []


def test_deleting_a_task_over_rest_puts_its_notices_away(client, app, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    assert client.delete(f"/tasks/{task['id']}", headers=h).status_code == 204
    assert inbox(client, h) == []
