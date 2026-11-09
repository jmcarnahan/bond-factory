"""The calendar mirror in fake mode honours the connection's state: expiry skips it, a reconnect brings a new calendar."""

import pytest
from connections_util import connect, headers, statuses
from tasks_util import make

from sdk_example.models.tasks import Task


@pytest.fixture
def h(client):
    return headers(client)


def expire(client, h, provider="fake-google"):
    reply = client.post(f"/connections/{provider}/simulate-expiry", headers=h)
    assert reply.status_code == 200 and reply.json()["needs_reconnect"] is True


def fetch(client, h, task_id):
    return client.get(f"/tasks/{task_id}", headers=h).json()


def test_editing_after_expiry_marks_the_mirror_skipped(client, h):
    connect(client, h)
    item = make(client, h, title="First", due_date="2026-11-09", due_time="09:00")
    assert fetch(client, h, item["id"])["mirror_status"] == "mirrored"
    expire(client, h)
    assert client.put(f"/tasks/{item['id']}", json={"title": "Second"}, headers=h).status_code == 200
    assert fetch(client, h, item["id"])["mirror_status"] == "skipped"


def test_a_new_task_after_expiry_is_skipped_too(client, h):
    connect(client, h)
    expire(client, h)
    item = make(client, h, due_date="2026-11-09")
    assert fetch(client, h, item["id"])["mirror_status"] == "skipped"


def test_the_calendar_route_reports_needs_reconnect(client, h):
    connect(client, h)
    expire(client, h)
    reply = client.get("/calendar/events", params={"start": "2026-11-01T00:00:00Z", "end": "2026-12-01T00:00:00Z"},
                       headers=h)
    assert reply.status_code == 409 and reply.json()["detail"]["code"] == "needs_reconnect"


def test_reconnect_then_edit_mirrors_again_under_a_new_external_id(client, app, h):
    connect(client, h)
    item = make(client, h, title="First", due_date="2026-11-09", due_time="09:00")
    first = fetch(client, h, item["id"])["external_event_id"]
    assert first and first.startswith("fake-")
    expire(client, h)
    client.put(f"/tasks/{item['id']}", json={"title": "Second"}, headers=h)
    assert connect(client, h).status_code == 302
    assert statuses(client, h)["fake-google"]["needs_reconnect"] is False
    client.put(f"/tasks/{item['id']}", json={"title": "Third"}, headers=h)
    after = fetch(client, h, item["id"])
    assert after["mirror_status"] == "mirrored" and after["external_event_id"] not in (None, first)
    with app.state.session_factory() as session:
        assert session.get(Task, item["id"]).external_event_id == after["external_event_id"]
