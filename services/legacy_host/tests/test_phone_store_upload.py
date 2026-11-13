"""The legacy phone store before the server changes: what `demos/legacy_phone` queues, replayed against this host.

`fixtures/legacy_host/upload_phone_store.json` (the table as shipped) and `upload_phone_store_widened.json` (after the app adds
the nine SDK columns) are recorded by `demos/legacy_phone/test/upload_fixture_test.dart`: a real local PowerSync database under
the SDK's task repository, laid over the app's own `tasks` table. They carry the app's column names (`sync_to_calendar`,
`client_ref`, `case_ref`, `case_file_no`) and never the module's `mirror_enabled`. The server needs no change to take them.
Each request is replayed alone and the server's state is checked after it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sync_util import load, raw, upload

FILES = ["upload_phone_store.json", "upload_phone_store_widened.json"]
HOST_CLOCK = "2026-11-08 10:00:00.000000"  # raw SQL reads the frozen host clock back as text


def steps(name: str) -> list[dict]:
    return load(name)["requests"]


def send(client, request: dict) -> dict:
    response = upload(client, request["user"], request["body"])
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert [r["status"] for r in results] == ["ok"] * len(request["body"]["ops"]), results
    return response.json()


def count(app, task_id: str) -> int:
    with app.state.engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM tasks WHERE id = :i"), {"i": task_id}).scalar()


@pytest.mark.parametrize("name", FILES)
def test_the_data_keys_are_the_apps_own_and_the_script_is_the_same(name):
    keys = {k for r in steps(name) for o in r["body"]["ops"] for k in o.get("data", {})}
    assert "mirror_enabled" not in keys
    assert {"sync_to_calendar", "client_ref", "case_ref", "case_file_no"} <= keys
    assert [o.get("action") for r in steps(name) for o in r["body"]["ops"]] == [None, None, "complete", "reopen", None, None]


@pytest.mark.parametrize("name", FILES)
def test_replayed_one_request_at_a_time_the_server_follows_each_step(app, client, name):
    reqs = steps(name)
    send(client, reqs[0])  # create
    assert raw(app, "ph-1", "title", "sync_to_calendar", "client_ref", "case_ref", "status", "owner_user_id") == (
        "Call the client", 1, "cl-1", "ca-1", "open", "u-owner")
    send(client, reqs[1])  # edit: new title, case cleared
    assert raw(app, "ph-1", "title", "client_ref", "case_ref") == ("Call the client back", "cl-1", None)
    send(client, reqs[2])  # complete
    assert raw(app, "ph-1", "status", "completed_by") == ("done", "u-owner")
    assert raw(app, "ph-1", "completed_at")[0] is not None
    send(client, reqs[3])  # reopen
    assert raw(app, "ph-1", "status", "completed_by", "completed_at") == ("open", None, None)
    send(client, reqs[4])  # a second task, flag off
    assert raw(app, "ph-2", "sync_to_calendar") == (0,)
    send(client, reqs[5])  # its delete
    assert count(app, "ph-2") == 0 and count(app, "ph-1") == 1


@pytest.mark.parametrize("name", FILES)
def test_the_server_owns_what_the_phone_only_guesses(app, client, name):
    reqs = steps(name)
    phone_put = reqs[0]["body"]["ops"][0]["data"]
    send(client, reqs[0])
    assert phone_put["created_at"] == "2026-03-11T20:00:00.000Z"
    assert raw(app, "ph-1", "created_at") == (HOST_CLOCK,)  # the host clock, not the phone's
    (mirror,) = raw(app, "ph-1", "mirror_status")
    assert phone_put["mirror_status"] == "pending" and mirror == "mirrored"  # the server's own result, not the phone's value
    with app.state.engine.connect() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))}
    assert "case_file_no" not in columns  # an unknown key: ignored, never stored
