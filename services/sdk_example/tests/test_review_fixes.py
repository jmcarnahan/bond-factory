"""Error codes the plan names, the event stub's limits, the app clock on sync, and the sweep script's arguments."""

import importlib.util
from pathlib import Path

import pytest
from bond_sync_py import Ctx, UploadRequest, upload
from connections_util import headers
from todo_util import inbox, sweep, timed

from sdk_example.capture_wiring import EventLog
from sdk_example.models.auth import DEMO_USER_ID
from sdk_example.routes.sync import build_host

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sweep_interval.py"


@pytest.fixture
def h(client):
    return headers(client)


def code(reply) -> str:
    return reply.json()["detail"]["code"]


@pytest.mark.parametrize("priority", [0, 4, 9, -1, "high", True, 1.5])
def test_a_bad_priority_is_422_invalid_priority_on_create_and_update(client, h, priority):
    reply = client.post("/tasks", json={"title": "x", "priority": priority}, headers=h)
    assert reply.status_code == 422 and code(reply) == "invalid_priority"
    task = client.post("/tasks", json={"title": "ok"}, headers=h).json()
    reply = client.put(f"/tasks/{task['id']}", json={"priority": priority}, headers=h)
    assert reply.status_code == 422 and code(reply) == "invalid_priority"


def test_a_good_or_null_priority_passes(client, h):
    assert client.post("/tasks", json={"title": "x", "priority": 3}, headers=h).json()["priority"] == 3
    assert client.post("/tasks", json={"title": "x", "priority": None}, headers=h).status_code == 201


@pytest.mark.parametrize("zone", ["Mars/Base", "", "UTC+99", 5])
def test_a_bad_zone_is_422_invalid_time_zone_everywhere(client, h, zone):
    task = client.post("/tasks", json={"title": "ok"}, headers=h).json()
    assert code(client.post("/tasks", json={"title": "x", "time_zone": zone}, headers=h)) == "invalid_time_zone"
    assert code(client.put(f"/tasks/{task['id']}", json={"time_zone": zone}, headers=h)) == "invalid_time_zone"
    assert code(client.put("/tasks/settings", json={"time_zone": zone}, headers=h)) == "invalid_time_zone"
    if isinstance(zone, str) and zone:
        for path in ("/tasks", "/tasks/today", "/tasks/summary", f"/tasks/{task['id']}"):
            reply = client.get(path, params={"time_zone": zone}, headers=h)
            assert reply.status_code == 422 and code(reply) == "invalid_time_zone", path


def test_other_body_errors_keep_the_generic_code(client, h):
    reply = client.post("/tasks", json={"priority": 2}, headers=h)  # no title
    assert reply.status_code == 422 and code(reply) != "invalid_priority"


EVENT = {"title": "Day off", "start_date": "2026-11-12", "all_day": True}


@pytest.mark.parametrize("bad", [
    {"title": ""}, {"title": "x" * 201}, {"start_date": "11/12/2026"}, {"start_date": "2026-11-12T00:00"},
    {"start_time": "25:00"}, {"end_date": "tomorrow"}, {"end_time": "9am"},
])
def test_the_event_stub_limits_its_strings(client, h, bad):
    assert client.post("/capture/events", json={**EVENT, **bad}, headers=h).status_code == 422


def test_the_event_stub_accepts_good_input_and_is_fake_mode_only(client, app, h):
    good = {**EVENT, "title": "x" * 200, "start_time": "09:30", "end_date": "2026-11-13", "end_time": "17:00"}
    assert client.post("/capture/events", json=good, headers=h).status_code == 201
    object.__setattr__(app.state.settings, "mode", "real")
    assert client.post("/capture/events", json=EVENT, headers=h).status_code == 404
    assert client.get("/capture/events", headers=h).status_code == 404


def test_event_ids_keep_counting_after_the_cap():
    log = EventLog(keep=3)
    ids = [log.add("u", {"title": str(n)})["id"] for n in range(6)]
    assert ids == [f"ev-{n}" for n in range(1, 7)] and len(log.items) == 3


def test_a_pinned_clock_stamps_sync_writes_too(client, app, h):
    timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    [notice] = inbox(client, h)
    client.put("/fake/clock", json={"now": "2026-11-09T09:45:00Z"}, headers=h)
    body = UploadRequest.model_validate({"transaction_id": 1, "ops": [
        {"seq": 0, "op": "patch", "table": "notices", "id": notice["id"], "action": None,
         "data": {"read_at": "2020-01-01T00:00:00Z"}}]})
    assert upload(app.state.session_factory, build_host(app), Ctx(user=DEMO_USER_ID), body).wire()["results"][0][
        "status"] == "ok"
    read = client.get("/notices", headers=h).json()["items"][0]["read_at"]
    assert read == "2026-11-09T09:45:00Z"


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("sweep_interval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("every", ["0", "0.5", "-3"])
def test_every_below_one_second_is_refused(script, every):
    with pytest.raises(SystemExit) as stop:
        script.main(["--every", every])
    assert stop.value.code == 2


def test_the_first_pass_prunes_and_then_once_an_hour(script):
    assert script.prune_due(None, 5.0) is True  # a small monotonic clock must not hide the first prune
    assert script.prune_due(5.0, 100.0) is False
    assert script.prune_due(5.0, 5.0 + script.PRUNE_EVERY) is True
