"""GET /tasks/today and the counts: one meaning of overdue (open and due_at < now), per viewer zone."""

from datetime import UTC, datetime

import pytest
from connections_util import headers
from todo_util import grant_write, timed

from sdk_example.models.auth import VIEWER_USER_ID

CHICAGO = "America/Chicago"  # UTC-6 on 2026-11-09, so 17:00 local is 23:00 UTC


def at(app, stamp: str) -> None:
    app.state.clock.freeze(datetime.fromisoformat(stamp).replace(tzinfo=UTC))


def titles(body, section) -> list[str]:
    return [t["title"] for t in body[section]]


@pytest.fixture
def h(client):
    return headers(client)


def test_a_task_due_at_five_pm_local_is_today_until_five_and_overdue_after(client, app, h):
    task = timed(client, h, title="Five", at="17:00", zone=CHICAGO)
    assert task["due_at"] == "2026-11-09T23:00:00Z"
    at(app, "2026-11-09T22:59:00")
    body = client.get("/tasks/today", params={"time_zone": CHICAGO}, headers=h).json()
    assert titles(body, "today") == ["Five"] and body["overdue"] == []
    assert body["counts"] == {"overdue": 0, "today": 1, "undated": 0, "done_today": 0}
    assert body["today"][0]["overdue"] is False
    assert client.get("/tasks/summary", params={"time_zone": CHICAGO}, headers=h).json() == {
        "open": 1, "overdue": 0, "due_today": 1, "no_date": 0}
    at(app, "2026-11-09T23:01:00")
    body = client.get("/tasks/today", params={"time_zone": CHICAGO}, headers=h).json()
    assert titles(body, "overdue") == ["Five"] and body["today"] == []
    assert body["overdue"][0]["overdue"] is True
    assert client.get("/tasks/summary", params={"time_zone": CHICAGO}, headers=h).json() == {
        "open": 1, "overdue": 1, "due_today": 0, "no_date": 0}
    listed = client.get("/tasks", params={"time_zone": CHICAGO}, headers=h).json()["items"]
    assert [t["overdue"] for t in listed] == [True]
    assert client.get(f"/tasks/{task['id']}", params={"time_zone": CHICAGO}, headers=h).json()["overdue"] is True


def test_the_sections_hold_undated_and_done_today(client, app, h):
    timed(client, h, title="Later", day="2026-11-20")
    client.post("/tasks", json={"title": "Someday"}, headers=h)
    finished = timed(client, h, title="Finished", day="2026-11-08", at="09:00")
    at(app, "2026-11-08T10:00:00")
    client.post(f"/tasks/{finished['id']}/complete", headers=h)
    body = client.get("/tasks/today", headers=h).json()
    assert titles(body, "undated") == ["Someday"] and titles(body, "done_today") == ["Finished"]
    assert body["today"] == [] and body["overdue"] == []  # "Later" is in no section
    assert body["counts"] == {"overdue": 0, "today": 0, "undated": 1, "done_today": 1}


def test_two_viewers_in_two_zones_see_the_same_task_in_different_sections(client, app, h):
    grant_write(app)
    other = headers(client, VIEWER_USER_ID)
    client.put("/tasks/settings", json={"time_zone": CHICAGO}, headers=h)
    client.put("/tasks/settings", json={"time_zone": "Pacific/Auckland"}, headers=other)
    timed(client, h, title="Shared", at="17:00", zone=CHICAGO, assigned_user_id=VIEWER_USER_ID)
    at(app, "2026-11-09T06:00:00")  # Chicago 00:00 on the 9th, Auckland 19:00 on the 9th
    chicago = client.get("/tasks/today", headers=h).json()
    auckland = client.get("/tasks/today", headers=other).json()
    assert titles(chicago, "today") == ["Shared"]
    assert auckland["today"] == []  # due 12:00 on the 10th there: a later day
    at(app, "2026-11-10T00:30:00")  # Chicago 18:30 on the 9th: overdue; Auckland 13:30 on the 10th: overdue too
    assert titles(client.get("/tasks/today", headers=h).json(), "overdue") == ["Shared"]
    assert titles(client.get("/tasks/today", headers=other).json(), "overdue") == ["Shared"]


def test_the_zone_falls_back_to_the_stored_setting_then_the_service_default(client, app, h):
    timed(client, h, title="Five", at="17:00", zone=CHICAGO)
    at(app, "2026-11-09T22:59:00")
    assert titles(client.get("/tasks/today", headers=h).json(), "today") == ["Five"]  # default zone UTC: 22:59 UTC
    client.put("/tasks/settings", json={"time_zone": "Asia/Tokyo"}, headers=h)  # 07:59 on the 10th
    assert titles(client.get("/tasks/today", headers=h).json(), "today") == ["Five"]  # due 08:00 on the 10th: today
    at(app, "2026-11-09T12:00:00")  # Tokyo 21:00 on the 9th: the task is due tomorrow there; Chicago 06:00 on the 9th
    assert client.get("/tasks/today", headers=h).json()["today"] == []
    assert titles(client.get("/tasks/today", params={"time_zone": CHICAGO}, headers=h).json(), "today") == ["Five"]


def test_a_bad_zone_is_422_and_today_is_not_read_as_a_task_id(client, h):
    reply = client.get("/tasks/today", params={"time_zone": "Mars/Base"}, headers=h)
    assert reply.status_code == 422 and reply.json()["detail"]["code"] == "invalid_time_zone"
    assert client.get("/tasks/today", headers=h).status_code == 200
