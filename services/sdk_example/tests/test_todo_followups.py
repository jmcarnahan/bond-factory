"""Inbox upkeep the libraries hand back to the host: settings that move deadlines, reassignment, finished tasks."""

import pytest
from bond_sync_py import Ctx, UploadRequest, upload
from connections_util import headers
from todo_util import inbox, sweep, timed

from sdk_example.models.auth import CREW_USER_ID, DEMO_USER_ID, VIEWER_USER_ID
from sdk_example.routes.sync import build_host


@pytest.fixture
def h(client):
    return headers(client)


def date_only_with_close_notice(client, h):
    client.put("/tasks/settings", json={"time_zone": "UTC"}, headers=h)
    task = client.post("/tasks", json={"title": "By evening", "due_date": "2026-11-09"}, headers=h).json()
    assert task["due_at"] == "2026-11-09T17:00:00Z"
    sweep(client, h, "2026-11-09T16:30:00Z")  # the close stage: 16:00 to 17:00
    assert [n["data"]["stage"] for n in inbox(client, h)] == ["close"]
    return task


def test_a_later_end_of_day_puts_the_old_close_notice_away_at_once(client, h):
    date_only_with_close_notice(client, h)
    client.put("/tasks/settings", json={"end_of_day": "19:00"}, headers=h)
    assert inbox(client, h) == []  # no tick needed


def test_a_zone_change_does_the_same(client, h):
    date_only_with_close_notice(client, h)
    client.put("/tasks/settings", json={"time_zone": "Asia/Tokyo"}, headers=h)
    assert inbox(client, h) == []


def test_a_settings_change_that_moves_nothing_keeps_the_notice(client, h):
    date_only_with_close_notice(client, h)
    client.put("/tasks/settings", json={"lead_minutes": 30}, headers=h)
    assert len(inbox(client, h)) == 1


def past_notices_for_crew_and_owner(client, h):
    crew = headers(client, CREW_USER_ID)
    task = timed(client, h, assigned_user_id=CREW_USER_ID)
    sweep(client, h, "2026-11-09T10:20:00Z")  # past goes to the assignee and the owner
    assert len(inbox(client, crew)) == 1 and len(inbox(client, h)) == 1
    return task, crew


def test_reassigning_puts_the_old_assignees_notice_away_and_keeps_the_owners(client, h):
    task, crew = past_notices_for_crew_and_owner(client, h)
    reply = client.put(f"/tasks/{task['id']}", json={"assigned_user_id": VIEWER_USER_ID}, headers=h)
    assert reply.status_code == 200 and reply.json()["due_at"] == task["due_at"]
    assert inbox(client, crew) == []
    assert len(inbox(client, h)) == 1


def test_reassigning_over_sync_does_the_same(client, app, h):
    task, crew = past_notices_for_crew_and_owner(client, h)
    body = UploadRequest.model_validate({"transaction_id": 1, "ops": [
        {"seq": 0, "op": "patch", "table": "tasks", "id": task["id"], "action": None,
         "data": {"assigned_user_id": VIEWER_USER_ID}}]})
    results = upload(app.state.session_factory, build_host(app), Ctx(user=DEMO_USER_ID), body).wire()["results"]
    assert results[0]["status"] == "ok"
    assert inbox(client, crew) == [] and len(inbox(client, h)) == 1


def test_acting_on_a_finished_task_is_a_no_op_that_still_reads_the_notice(client, h):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    notice = inbox(client, h)[0]
    client.post(f"/tasks/{task['id']}/complete", headers=h)
    reply = client.post(f"/notices/{notice['id']}/act", json={"action": "cancel"}, headers=h)
    assert reply.status_code == 200
    body = reply.json()
    assert body["task"]["status"] == "done" and body["notice"]["read_at"] is not None


def test_a_garbage_due_at_is_ignored_and_computed(client, h):
    reply = client.post("/tasks", json={"title": "x", "due_date": "2026-11-09", "due_time": "10:00",
                                        "time_zone": "UTC", "due_at": "not a time"}, headers=h)
    assert reply.status_code == 201 and reply.json()["due_at"] == "2026-11-09T10:00:00Z"
