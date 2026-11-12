"""POST /push/devices and DELETE /push/devices/{device_id}; the pushes the sweep sends to a registered phone."""

import pytest
from bond_push_py import PushResult, device_row_id
from connections_util import headers
from fastapi.testclient import TestClient
from todo_util import pushed, register_phone, sweep, timed

from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID
from sdk_example.models.push import PushDevice


@pytest.fixture
def h(client):
    return headers(client)


def body(**over):
    return {"device_id": "dev-1", "token": "tok-1", "platform": "ios", "environment": "sandbox",
            "topic": "org.example.app", **over}


def rows(app):
    with app.state.session_factory() as session:
        return session.query(PushDevice).order_by(PushDevice.device_id).all()


def test_register_is_201_and_the_user_comes_from_the_session(client, app, h):
    reply = client.post("/push/devices", json=body(), headers=h)
    assert reply.status_code == 201 and reply.json() == {"device_id": "dev-1"}
    [row] = rows(app)
    assert (row.user_id, row.token, row.environment, row.topic) == (DEMO_USER_ID, "tok-1", "sandbox", "org.example.app")
    assert row.id == device_row_id(DEMO_USER_ID, "dev-1")
    assert client.post("/push/devices", json=body(user_id="demo-user-2"), headers=h).status_code == 422  # not a field


def test_registering_again_updates_the_row(client, app, h):
    client.post("/push/devices", json=body(), headers=h)
    client.post("/push/devices", json=body(token="tok-2", environment="production"), headers=h)
    [row] = rows(app)
    assert (row.token, row.environment) == ("tok-2", "production")


def test_a_token_that_changes_hands_moves(client, app, h):
    client.post("/push/devices", json=body(), headers=h)
    other = headers(client, VIEWER_USER_ID)
    assert client.post("/push/devices", json=body(device_id="dev-9"), headers=other).status_code == 201
    [row] = rows(app)
    assert (row.user_id, row.device_id) == (VIEWER_USER_ID, "dev-9")


@pytest.mark.parametrize("field, value, code", [
    ("platform", "palm", "invalid_platform"), ("environment", "staging", "invalid_environment"),
    ("token", " ", "token_required"), ("device_id", "", "device_id_required"),
])
def test_bad_input_is_a_coded_422(client, h, field, value, code):
    reply = client.post("/push/devices", json=body(**{field: value}), headers=h)
    assert reply.status_code == 422 and reply.json()["detail"]["code"] == code


def test_unregister_is_204_scoped_to_the_caller_and_idempotent(client, app, h):
    client.post("/push/devices", json=body(), headers=h)
    other = headers(client, VIEWER_USER_ID)
    assert client.delete("/push/devices/dev-1", headers=other).status_code == 204
    assert len(rows(app)) == 1  # someone else's device id removes nothing
    assert client.delete("/push/devices/dev-1", headers=h).status_code == 204
    assert client.delete("/push/devices/dev-1", headers=h).status_code == 204
    assert rows(app) == []


def test_it_needs_a_session(app):
    assert TestClient(app).post("/push/devices", json=body()).status_code == 401
    assert TestClient(app).delete("/push/devices/dev-1").status_code == 401


def test_a_sweep_pushes_to_every_device_and_a_dead_token_is_disabled(client, app, h):
    register_phone(client, h, token="tok-a", device_id="a")
    register_phone(client, h, token="tok-b", device_id="b")
    app.state.push_sender.fail_tokens["tok-b"] = PushResult(ok=False, unregistered=True)
    task = timed(client, h)
    sweep(client, h, "2026-11-09T10:05:00Z")
    assert sorted(m["token"] for m in pushed(client, h, task["id"])) == ["tok-a", "tok-b"]
    live = {r.device_id: r.disabled_at is None for r in rows(app)}
    assert live == {"a": True, "b": False}
    assert all(m["title"] and m["thread_id"] == task["id"] and m["category"] is None for m in pushed(client, h))


def test_a_user_with_no_phone_still_gets_the_inbox_notice(client, app, h):
    task = timed(client, h)
    body = sweep(client, h, "2026-11-09T10:05:00Z")
    assert body["sweep"]["claimed"] == 1 and body["deliver"]["sent"] == 1
    assert pushed(client, h, task["id"]) == []
    assert client.get("/notices", headers=h).json()["unread_count"] == 1
