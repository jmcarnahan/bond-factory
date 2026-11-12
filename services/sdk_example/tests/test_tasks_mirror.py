"""The calendar mirror and the lib's sync routes under the example's own sync host, over a fake-mode app."""

import pytest
from connections_util import connect, headers
from tasks_util import TODAY, make

from sdk_example.models.auth import DEMO_USER_ID
from sdk_example.models.tasks import Task


@pytest.fixture
def h(client):
    return headers(client)


def test_mirror_shows_the_external_id_for_fake_google(client, h):
    assert connect(client, h, "fake-google").status_code == 302
    item = make(client, h, due_date="2026-11-09", due_time="09:00")
    fresh = client.get(f"/tasks/{item['id']}", headers=h).json()
    assert (fresh["mirror_status"], fresh["external_provider"]) == ("mirrored", "google")
    assert fresh["external_event_id"].startswith("fake-")


def test_mirror_uses_microsoft_when_that_is_the_connection(client, h):
    connect(client, h, "fake-microsoft")
    item = make(client, h, due_date="2026-11-09")
    fresh = client.get(f"/tasks/{item['id']}", headers=h).json()
    assert (fresh["mirror_status"], fresh["external_provider"]) == ("mirrored", "microsoft")


def test_mirror_is_skipped_without_a_connection_and_when_switched_off(client, h):
    assert make(client, h, due_date="2026-11-09")["mirror_status"] == "pending"
    item = client.get("/tasks", headers=h).json()["items"][0]
    assert (item["mirror_status"], item["external_event_id"]) == ("skipped", None)
    connect(client, h, "fake-google")
    off = make(client, h, due_date="2026-11-09", mirror_enabled=False)
    assert client.get(f"/tasks/{off['id']}", headers=h).json()["mirror_status"] == "skipped"


def test_completing_removes_the_mirrored_event_and_delete_cleans_up(client, app, h):
    connect(client, h, "fake-google")
    item = make(client, h, due_date="2026-11-09")
    calendar = next(iter(app.state.fake_calendars.values()))
    assert len(calendar.events) == 1
    done = client.post(f"/tasks/{item['id']}/complete", headers=h)
    assert done.status_code == 200 and calendar.events == []
    fresh = client.get(f"/tasks/{item['id']}", headers=h).json()
    assert (fresh["mirror_status"], fresh["external_event_id"]) == ("skipped", None)
    client.post(f"/tasks/{item['id']}/reopen", headers=h)
    assert len(calendar.events) == 1
    assert client.delete(f"/tasks/{item['id']}", headers=h).status_code == 204
    assert calendar.events == []


def test_the_libs_sync_routes_run_under_the_sync_dispatcher(app):
    from bond_sync_py import Ctx, UploadRequest, upload

    from sdk_example.routes.sync import build_host

    def op(seq, kind, id_, data=None, action=None):
        return {"seq": seq, "op": kind, "table": "tasks", "id": id_, "action": action, "data": data or {}}

    body = UploadRequest.model_validate({"transaction_id": 1, "ops": [
        op(0, "put", "dev-1", {"title": "From a device", "due_date": TODAY, "remind_minutes_before": 0,
                               "due_time": "11:00"}),
        op(1, "patch", "dev-1", {"title": "Renamed"}),
        op(2, "patch", "dev-1", action="complete"),
        op(3, "put", "dev-2", {}),
        op(4, "patch", "missing", {"title": "x"}),
        op(5, "delete", "dev-1"),
    ]})
    results = upload(app.state.session_factory, build_host(app), Ctx(user=DEMO_USER_ID), body).wire()["results"]
    assert [r["status"] for r in results] == ["ok", "ok", "ok", "rejected", "rejected", "ok"]
    assert (results[3]["code"], results[3]["message"]) == ("invalid", "title_required")
    assert (results[4]["code"], results[4]["message"]) == ("not_found", "task_not_found")
    with app.state.session_factory() as session:
        assert session.get(Task, "dev-1") is None


def test_editing_a_mirrored_task_updates_the_event_with_its_etag(client, app, h):
    connect(client, h, "fake-google")
    item = make(client, h, title="First", due_date="2026-11-09")
    client.put(f"/tasks/{item['id']}", json={"title": "Second"}, headers=h)
    calendar = next(iter(app.state.fake_calendars.values()))
    assert [e.subject for e in calendar.events] == ["Second"]
    with app.state.session_factory() as session:
        assert session.get(Task, item["id"]).external_etag == calendar.events[0].etag
