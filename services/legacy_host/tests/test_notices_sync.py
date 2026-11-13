"""Notices over `POST /sync/upload`: the phone marks its own notice read or dismissed with a patch; the server stamps."""

from __future__ import annotations

from datetime import UTC, datetime

from bond_push_py import device_row_id
from sqlalchemy import text
from sync_util import load, replay, upload

from legacy_host.models import Notice

CLOCK = "2026-11-08 10:00:00.000000"  # raw SQL reads a naive instant back as text
LATER = datetime(2026, 11, 9, 8, 30, tzinfo=UTC)
LATER_TEXT = "2026-11-09 08:30:00.000000"
OK = {"status": "ok"}
DEVICE_TIME = "2026-11-08T10:00:00.000Z"  # the dispatcher parses a datetime column; the server ignores the value


def add_notice(app, notice_id: str, user: str = "u-owner") -> None:
    with app.state.session_factory() as session:
        session.add(Notice(id=notice_id, user_id=user, kind="task_due", title="Due", body="b", data={},
                           created_at=datetime(2026, 11, 7, 9, 0)))
        session.commit()


def stamps(app, notice_id: str) -> tuple:
    with app.state.engine.connect() as conn:
        return tuple(conn.execute(text("SELECT read_at, dismissed_at FROM notices WHERE id = :i"), {"i": notice_id}).one())


def patch(seq: int, notice_id: str, **data) -> dict:
    return {"seq": seq, "op": "patch", "table": "notices", "id": notice_id, "data": data}


def send(client, user: str, *ops: dict) -> list[dict]:
    response = upload(client, user, {"transaction_id": 1, "ops": list(ops)})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def refused(seq: int, code: str, message: str) -> dict:
    return {"seq": seq, "status": "rejected", "code": code, "message": message}


def test_read_stores_the_host_clock_not_the_devices(app, client):
    add_notice(app, "n1")
    assert send(client, "u-owner", patch(0, "n1", read_at="2001-01-01T00:00:00.000Z")) == [{"seq": 0, **OK}]
    assert stamps(app, "n1") == (CLOCK, None)


def test_the_first_stamp_is_kept_when_the_patch_is_repeated_with_another_time(app, client):
    add_notice(app, "n1")
    send(client, "u-owner", patch(0, "n1", read_at="2026-11-08T10:00:00.000Z"))
    app.state.clock.freeze(LATER)
    assert send(client, "u-owner", patch(0, "n1", read_at="2030-01-01T00:00:00.000Z")) == [{"seq": 0, **OK}]
    assert stamps(app, "n1") == (CLOCK, None)


def test_dismiss_also_reads_and_keeps_an_earlier_read_stamp(app, client):
    add_notice(app, "n1")
    add_notice(app, "n2")
    send(client, "u-owner", patch(0, "n2", read_at=DEVICE_TIME))
    app.state.clock.freeze(LATER)
    assert send(client, "u-owner", patch(0, "n1", dismissed_at=DEVICE_TIME), patch(1, "n2", dismissed_at=DEVICE_TIME)) == [
        {"seq": 0, **OK}, {"seq": 1, **OK}]
    assert stamps(app, "n1") == (LATER_TEXT, LATER_TEXT)
    assert stamps(app, "n2") == (CLOCK, LATER_TEXT)


def test_a_null_clears_nothing(app, client):
    add_notice(app, "n1")
    send(client, "u-owner", patch(0, "n1", read_at=DEVICE_TIME))
    assert send(client, "u-owner", patch(0, "n1", read_at=None, dismissed_at=None)) == [{"seq": 0, **OK}]
    assert stamps(app, "n1") == (CLOCK, None)


def test_another_users_notice_is_refused_and_untouched(app, client):
    add_notice(app, "n1", user="u-owner")
    assert send(client, "u-editor", patch(0, "n1", read_at=DEVICE_TIME, dismissed_at=DEVICE_TIME)) == [
        refused(0, "forbidden", "not_notice_owner")]
    assert stamps(app, "n1") == (None, None)


def test_an_unknown_notice_is_not_found(client):
    assert send(client, "u-owner", patch(0, "nope", read_at=DEVICE_TIME)) == [refused(0, "not_found", "notice_not_found")]


def test_read_all_is_one_patch_per_row_in_one_upload(app, client):
    for n in ("n1", "n2", "n3"):
        add_notice(app, n)
    ops = [patch(i, n, read_at=DEVICE_TIME) for i, n in enumerate(("n1", "n2", "n3"))]
    assert send(client, "u-owner", *ops) == [{"seq": i, **OK} for i in range(3)]
    assert [stamps(app, n) for n in ("n1", "n2", "n3")] == [(CLOCK, None)] * 3


def test_a_device_cannot_put_or_delete_a_notice(app, client):
    add_notice(app, "n1")
    put = {"seq": 0, "op": "put", "table": "notices", "id": "n9",
           "data": {"user_id": "u-owner", "kind": "task_due", "title": "x", "body": "y"}}
    delete = {"seq": 1, "op": "delete", "table": "notices", "id": "n1"}
    answers = send(client, "u-owner", put, delete)
    unsupported = {"status": "rejected", "code": "unsupported", "message": "Not supported"}
    assert answers == [{"seq": 0, **unsupported}, {"seq": 1, **unsupported}]  # the lib offers the patch only
    with app.state.engine.connect() as conn:
        assert [r[0] for r in conn.execute(text("SELECT id FROM notices"))] == ["n1"]


def test_an_old_client_that_sends_no_notice_ops_is_unaffected(app, client):
    answers = replay(client, load("upload_old_client.json"))
    assert [{"results": a["results"]} for a in answers] == load("upload_old_client_expected.json")["answers"]


def test_task_notice_and_device_ops_in_one_upload(app, client):
    add_notice(app, "n1")
    task = {"seq": 0, "op": "put", "table": "tasks", "id": "t-mix", "data": {"title": "Mixed", "sync_to_calendar": 0}}
    device = {"seq": 2, "op": "put", "table": "push_devices", "id": device_row_id("u-owner", "device-1"), "data": {
        "device_id": "device-1", "token": "a" * 64, "platform": "ios", "environment": "sandbox"}}
    assert send(client, "u-owner", task, patch(1, "n1", read_at=DEVICE_TIME), device) == [
        {"seq": 0, **OK}, {"seq": 1, **OK}, {"seq": 2, **OK}]
    assert stamps(app, "n1") == (CLOCK, None)
