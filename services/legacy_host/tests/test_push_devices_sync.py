"""Push devices over `POST /sync/upload`: the phone writes its own `push_devices` row (no REST route exists)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bond_push_py import device_row_id
from fastapi.testclient import TestClient
from legacy_db import legacy_app
from sqlalchemy import text
from sync_util import load, replay, upload

from legacy_host.models import PushDevice

CLOCK = "2026-11-08 10:00:00.000000"  # raw SQL reads a naive instant back as text
TOKEN_A = "a" * 64
TOKEN_B = "b" * 64
TOKEN_C = "c" * 64


def device_put(user: str, device: str = "device-1", token: str = TOKEN_A, seq: int = 0, **over) -> dict:
    data = {"user_id": user, "device_id": device, "token": token, "platform": "ios", "environment": "sandbox",
            "topic": "com.example.app", "last_seen_at": "2020-01-01T00:00:00.000Z", "created_at": "2020-01-01T00:00:00.000Z"}
    data.update(over)
    return {"seq": seq, "op": "put", "table": "push_devices", "id": device_row_id(user, device), "data": data}


def send(client, user: str, *ops: dict) -> list[dict]:
    response = upload(client, user, {"transaction_id": 1, "ops": list(ops)})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def rows(app) -> dict[str, tuple]:
    """id -> (user_id, device_id, token, last_seen_at, disabled_at, created_at), by raw SQL."""
    with app.state.engine.connect() as conn:
        found = conn.execute(text("SELECT id, user_id, device_id, token, last_seen_at, disabled_at, created_at "
                                  "FROM push_devices")).all()
    return {r[0]: tuple(r[1:]) for r in found}


def refused(seq: int, code: str, message: str) -> dict:
    return {"seq": seq, "status": "rejected", "code": code, "message": message}


OK0 = {"seq": 0, "status": "ok"}


# the recorded phone session

def test_the_recorded_session_registers_refreshes_and_unregisters(app, client):
    answers = replay(client, load("upload_push_devices.json"))
    assert [a["results"] for a in answers] == [[OK0], [OK0], [OK0]]
    assert rows(app) == {}  # unregister deletes the row


def test_register_takes_user_from_the_session_and_stamps_the_host_clock(app, client):
    recording = load("upload_push_devices.json")
    first = recording["requests"][0]
    assert send(client, first["user"], *first["body"]["ops"]) == [OK0]
    row_id = device_row_id("u-owner", "device-1")
    assert rows(app) == {row_id: ("u-owner", "device-1", TOKEN_A, CLOCK, None, CLOCK)}  # the payload said 2026-11-12T15


def test_refresh_changes_the_token_and_last_seen_comes_from_the_host_clock(app, client):
    recording = load("upload_push_devices.json")
    send(client, "u-owner", *recording["requests"][0]["body"]["ops"])
    app.state.clock.freeze(datetime(2026, 11, 9, 8, 30, tzinfo=UTC))
    patch = dict(recording["requests"][1]["body"]["ops"][0], data={"token": TOKEN_B, "last_seen_at": "2001-01-01T00:00:00Z"})
    assert send(client, "u-owner", patch) == [OK0]
    assert rows(app)[device_row_id("u-owner", "device-1")] == ("u-owner", "device-1", TOKEN_B, "2026-11-09 08:30:00.000000", None, CLOCK)


def test_unregister_deletes_the_row_and_a_second_delete_is_still_ok(app, client):
    send(client, "u-owner", device_put("u-owner"))
    delete = {"seq": 0, "op": "delete", "table": "push_devices", "id": device_row_id("u-owner", "device-1")}
    assert send(client, "u-owner", delete) == [OK0]
    assert rows(app) == {}
    assert send(client, "u-owner", delete) == [OK0]


# ownership

def test_a_payload_user_id_naming_another_user_is_ignored(app, client):
    op = device_put("u-owner", user_id="u-stranger")
    assert send(client, "u-owner", op) == [OK0]
    assert [r[0] for r in rows(app).values()] == ["u-owner"]


def test_another_users_formula_id_is_refused_and_the_row_is_untouched(app, client):
    send(client, "u-owner", device_put("u-owner"))
    before = rows(app)
    stolen = device_put("u-owner", token=TOKEN_B)  # B puts with A's id
    row_id = stolen["id"]
    patch = {"seq": 1, "op": "patch", "table": "push_devices", "id": row_id, "data": {"token": TOKEN_C}}
    delete = {"seq": 2, "op": "delete", "table": "push_devices", "id": row_id}
    assert send(client, "u-editor", stolen, patch, delete) == [
        refused(0, "forbidden", "not_device_owner"), refused(1, "forbidden", "not_device_owner"),
        refused(2, "forbidden", "not_device_owner")]
    assert rows(app) == before


def test_a_new_row_must_carry_the_callers_own_formula_id(app, client):
    op = dict(device_put("u-owner"), id="d_made_up")
    assert send(client, "u-owner", op) == [refused(0, "forbidden", "not_device_owner")]
    assert rows(app) == {}


def test_a_patch_of_a_row_that_does_not_exist_is_not_found(app, client):
    patch = {"seq": 0, "op": "patch", "table": "push_devices", "id": device_row_id("u-owner", "device-9"),
             "data": {"token": TOKEN_B}}
    assert send(client, "u-owner", patch) == [refused(0, "not_found", "device_not_found")]


def test_a_token_held_by_another_users_row_moves_to_the_new_registrant(app, client):
    send(client, "u-owner", device_put("u-owner", token=TOKEN_A))
    assert send(client, "u-editor", device_put("u-editor", device="phone-2", token=TOKEN_A)) == [OK0]
    assert rows(app) == {device_row_id("u-editor", "phone-2"): ("u-editor", "phone-2", TOKEN_A, CLOCK, None, CLOCK)}


# bad input: a per-op verdict in a 200, the rest of the upload applies

BAD = [
    ("platform", {"platform": "android"}, "invalid_platform"),
    ("missing token", {"token": None}, "token_required"),
    ("blank token", {"token": "  "}, "token_required"),
    ("non-string token", {"token": 12345}, "invalid"),  # the dispatcher's column coercion refuses it first
    ("long token", {"token": "t" * 256}, "token_too_long"),
    ("environment", {"environment": "staging"}, "invalid_environment"),
    ("non-string topic", {"topic": 7}, "invalid"),
]


@pytest.mark.parametrize(("name", "over", "message"), BAD, ids=[b[0] for b in BAD])
def test_bad_input_is_a_verdict_and_the_good_op_still_applies(app, client, name, over, message):
    good = device_put("u-owner", device="device-2", token=TOKEN_C, seq=1)
    assert send(client, "u-owner", device_put("u-owner", **over), good) == [refused(0, "invalid", message), {"seq": 1, "status": "ok"}]
    assert list(rows(app)) == [device_row_id("u-owner", "device-2")]


def test_an_over_long_device_id_is_a_verdict(app, client):
    long_id = "d" * 65
    good = device_put("u-owner", seq=1)
    assert send(client, "u-owner", device_put("u-owner", device=long_id), good) == [
        refused(0, "invalid", "device_id_too_long"), {"seq": 1, "status": "ok"}]
    assert len(rows(app)) == 1


def test_a_missing_device_id_is_a_verdict(app, client):
    op = device_put("u-owner")
    del op["data"]["device_id"]
    assert send(client, "u-owner", op) == [refused(0, "invalid", "device_id_required")]
    assert rows(app) == {}


def test_a_patch_with_a_bad_value_is_a_verdict_and_leaves_the_row(app, client):
    send(client, "u-owner", device_put("u-owner"))
    before = rows(app)
    patch = {"seq": 0, "op": "patch", "table": "push_devices", "id": device_row_id("u-owner", "device-1"),
             "data": {"platform": "web"}}
    assert send(client, "u-owner", patch) == [refused(0, "invalid", "invalid_platform")]
    assert rows(app) == before


# old clients, and an adopted database

def test_one_upload_may_carry_a_task_and_a_device(app, client):
    task = {"seq": 0, "op": "put", "table": "tasks", "id": "t-mix", "data": {"title": "Mixed", "sync_to_calendar": 0}}
    assert send(client, "u-owner", task, dict(device_put("u-owner"), seq=1)) == [OK0, {"seq": 1, "status": "ok"}]
    assert len(rows(app)) == 1
    with app.state.session_factory() as session:
        assert session.get(PushDevice, device_row_id("u-owner", "device-1")) is not None


def test_a_task_refusal_keeps_its_task_verdict_next_to_a_push_one(client):
    task = {"seq": 0, "op": "patch", "table": "tasks", "id": "missing", "data": {"title": "x"}}
    results = send(client, "u-owner", task, device_put("u-owner", seq=1, platform="android"))
    assert results[0] == refused(0, "not_found", "task_not_found")
    assert results[1] == refused(1, "invalid", "invalid_platform")


def test_the_adopted_database_accepts_a_registration(tmp_path):
    app = legacy_app(tmp_path / "old.db")
    client = TestClient(app)
    assert send(client, "u-owner", device_put("u-owner")) == [OK0]
    assert rows(app)[device_row_id("u-owner", "device-1")][:3] == ("u-owner", "device-1", TOKEN_A)
    assert replay(client, load("upload_push_devices.json"))[-1]["results"] == [OK0]
