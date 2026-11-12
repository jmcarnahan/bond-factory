"""POST /notices/{id}/act: done, snooze and cancel, and who may do what."""

import pytest
from connections_util import headers
from fastapi.testclient import TestClient
from todo_util import grant_write, inbox, notices_of, sweep, timed

from sdk_example.models.auth import VIEWER_USER_ID

SOON = "2026-11-09T09:30:00Z"  # inside the close stage of a task due 10:00 UTC


@pytest.fixture
def h(client):
    return headers(client)


def first_notice(client, h) -> dict:
    sweep(client, h, SOON)
    return inbox(client, h)[0]


def act(client, h, notice, action, **params):
    return client.post(f"/notices/{notice['id']}/act", json={"action": action}, params=params, headers=h)


def test_done_completes_reads_and_puts_away_every_notice_of_the_task(client, app, h):
    task = timed(client, h)
    sweep(client, h, SOON)
    sweep(client, h, "2026-11-09T10:05:00Z")  # a second notice (due) for the same task
    notice = inbox(client, h)[0]
    reply = act(client, h, notice, "done")
    assert reply.status_code == 200
    body = reply.json()
    assert body["task"]["id"] == task["id"] and body["task"]["status"] == "done"
    assert body["notice"]["id"] == notice["id"] and body["notice"]["read_at"] is not None
    assert inbox(client, h) == []
    assert all(n.read_at and n.dismissed_at for n in notices_of(app, task["id"]))


def test_snooze_changes_nothing_on_the_task_and_reads_the_notice(client, app, h):
    task = timed(client, h)
    notice = first_notice(client, h)
    body = act(client, h, notice, "snooze").json()
    assert body["task"]["status"] == "open" and body["notice"]["read_at"] is not None
    assert body["notice"]["dismissed_at"] is None
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["status"] == "open"


def test_cancel_by_the_owner_cancels_and_puts_away(client, app, h):
    task = timed(client, h)
    notice = first_notice(client, h)
    body = act(client, h, notice, "cancel").json()
    assert body["task"]["status"] == "cancelled"
    assert inbox(client, h) == [] and all(n.dismissed_at for n in notices_of(app, task["id"]))


def test_cancel_by_someone_who_is_not_the_owner_is_403_and_changes_nothing(client, app, h):
    grant_write(app)
    viewer = headers(client, VIEWER_USER_ID)
    task = timed(client, h, assigned_user_id=VIEWER_USER_ID)
    sweep(client, h, SOON)
    mine = inbox(client, viewer)
    assert [n["data"]["actions"] for n in mine] == [["done", "snooze"]]  # no cancel for an assignee
    reply = act(client, viewer, mine[0], "cancel")
    assert reply.status_code == 403 and reply.json()["detail"]["code"] == "not_task_owner"
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["status"] == "open"
    assert inbox(client, viewer)[0]["read_at"] is None  # the refusal rolled back with the rest
    assert act(client, viewer, mine[0], "done").json()["task"]["status"] == "done"


def test_another_persons_notice_is_403(client, app, h):
    grant_write(app)
    timed(client, h)
    notice = first_notice(client, h)
    reply = act(client, headers(client, VIEWER_USER_ID), notice, "done")
    assert reply.status_code == 403 and reply.json()["detail"]["code"] == "not_notice_owner"


def test_an_unknown_notice_is_404_and_a_bad_action_is_422(client, h):
    reply = client.post("/notices/nope/act", json={"action": "done"}, headers=h)
    assert reply.status_code == 404 and reply.json()["detail"]["code"] == "notice_not_found"
    assert client.post("/notices/nope/act", json={"action": "explode"}, headers=h).status_code == 422


def test_the_notice_routes_read_dismiss_and_page(client, app, h):
    for index in range(3):
        timed(client, h, title=f"t{index}", at="10:00")
    sweep(client, h, SOON)
    listing = client.get("/notices", params={"limit": 2}, headers=h).json()
    assert len(listing["items"]) == 2 and listing["unread_count"] == 3 and listing["next_cursor"]
    rest = client.get("/notices", params={"limit": 2, "before": listing["next_cursor"]}, headers=h).json()
    assert len(rest["items"]) == 1
    one = listing["items"][0]
    assert client.post(f"/notices/{one['id']}/read", headers=h).json()["read_at"] is not None
    assert client.get("/notices", params={"unread": True}, headers=h).json()["unread_count"] == 2
    assert client.post(f"/notices/{one['id']}/dismiss", headers=h).json()["dismissed_at"] is not None
    assert client.post("/notices/read-all", headers=h).json() == {"unread_count": 0}
    assert len(inbox(client, h)) == 2
    assert TestClient(app).get("/notices").status_code == 401
