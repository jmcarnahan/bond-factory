"""Reminders through the job queue, the calendar mirror and the lib's sync routes, over a fake-mode app."""

from datetime import datetime

import pytest
from connections_util import connect, headers
from tasks_util import T0, TODAY, make, tick

from sdk_example import wiring
from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID
from sdk_example.models.jobs import BackgroundJob
from sdk_example.models.tasks import Task


@pytest.fixture
def h(client):
    return headers(client)


def test_reminder_fires_once_through_the_job_queue(client, app, h):
    wiring.set_now(app, T0)
    item = make(client, h, title="Ring", due_date=TODAY, due_time="10:01", remind_minutes_before=0)
    wiring.set_now(app, None)
    assert item["remind_at"] == "2026-11-08T10:01:00Z"
    assert client.get("/tasks/notices", headers=h).json() == {"items": []}
    assert tick(client, h, "2026-11-08T10:00:30Z") == []  # not due yet
    ran = tick(client, h, "2026-11-08T10:02:00Z")
    assert [(r["job_type"], r["status"]) for r in ran] == [("task_reminder", "done")]
    notices = client.get("/tasks/notices", headers=h).json()["items"]
    assert [(n["task_id"], n["message"]) for n in notices] == [(item["id"], "Reminder: Ring")]
    assert tick(client, h, "2026-11-08T10:03:00Z") == []  # no second run
    assert len(client.get("/tasks/notices", headers=h).json()["items"]) == 1
    assert client.get(f"/tasks/{item['id']}", headers=h).json()["reminded_at"] == "2026-11-08T10:02:00Z"


def test_moving_the_due_time_reschedules_one_job(client, app, h):
    item = make(client, h, due_date=TODAY, due_time="10:01", remind_minutes_before=0)
    client.put(f"/tasks/{item['id']}", json={"due_time": "10:30"}, headers=h)
    with app.state.session_factory() as session:
        rows = session.query(BackgroundJob).filter_by(job_type="task_reminder").all()
        assert [(r.idempotency_key, r.run_at) for r in rows] == [
            (f"task_reminder:{item['id']}", datetime(2026, 11, 8, 10, 30))]
    assert tick(client, h, "2026-11-08T10:05:00Z") == []
    assert len(tick(client, h, "2026-11-08T10:31:00Z")) == 1


def test_a_moved_reminder_fires_again_after_it_already_ran(client, h):
    item = make(client, h, due_date=TODAY, due_time="10:01", remind_minutes_before=0)
    assert len(tick(client, h, "2026-11-08T10:02:00Z")) == 1
    client.put(f"/tasks/{item['id']}", json={"due_time": "11:00"}, headers=h)
    assert len(tick(client, h, "2026-11-08T11:01:00Z")) == 1
    assert len(client.get("/tasks/notices", headers=h).json()["items"]) == 2


def test_completing_or_deleting_withdraws_the_reminder(client, app, h):
    done = make(client, h, due_date=TODAY, due_time="10:01", remind_minutes_before=0)
    gone = make(client, h, due_date=TODAY, due_time="10:01", remind_minutes_before=0)
    client.post(f"/tasks/{done['id']}/complete", headers=h)
    client.delete(f"/tasks/{gone['id']}", headers=h)
    with app.state.session_factory() as session:
        assert session.query(BackgroundJob).filter_by(job_type="task_reminder").count() == 0
    assert tick(client, h, "2026-11-08T10:30:00Z") == []
    assert client.get("/tasks/notices", headers=h).json()["items"] == []


def test_notices_are_per_person_and_fake_only(client, app, h):
    make(client, h, due_date=TODAY, due_time="10:01", remind_minutes_before=0)
    tick(client, h, "2026-11-08T10:02:00Z")
    assert client.get("/tasks/notices", headers=headers(client, VIEWER_USER_ID)).json() == {"items": []}
    object.__setattr__(app.state.settings, "mode", "real")
    assert client.get("/tasks/notices", headers=h).status_code == 404


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


def sync_host(app):
    """The lib's routes wrapped as the sync lib's Routes: what routes/sync.py does when tasks are synced."""
    from bond_sync_py import Host, Route, rejected
    from bond_tasks_py import sync_routes, verdict_for

    def reject_for(session, user, op, exc):
        verdict = verdict_for(exc)
        return rejected(op.seq, verdict[0], verdict[1]) if verdict else None

    routes = sync_routes(Task, scheduler=app.state.tasks_scheduler)
    return Host(routes={key: Route(r.ops, r.handler, r.reads) for key, r in routes.items()},
                tables={"tasks": Task.__table__}, single_action=frozenset({"tasks"}), reject_for=reject_for)


def test_the_libs_sync_routes_run_under_the_sync_dispatcher(app):
    from bond_sync_py import Ctx, UploadRequest, upload

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
    results = upload(app.state.session_factory, sync_host(app), Ctx(user=DEMO_USER_ID), body).wire()["results"]
    assert [r["status"] for r in results] == ["ok", "ok", "ok", "rejected", "rejected", "ok"]
    assert (results[3]["code"], results[3]["message"]) == ("invalid", "title_required")
    assert (results[4]["code"], results[4]["message"]) == ("not_found", "task_not_found")
    with app.state.session_factory() as session:
        assert session.get(Task, "dev-1") is None
        assert session.query(BackgroundJob).count() == 0  # the reminder was withdrawn with the task


def test_editing_a_mirrored_task_updates_the_event_with_its_etag(client, app, h):
    connect(client, h, "fake-google")
    item = make(client, h, title="First", due_date="2026-11-09")
    client.put(f"/tasks/{item['id']}", json={"title": "Second"}, headers=h)
    calendar = next(iter(app.state.fake_calendars.values()))
    assert [e.subject for e in calendar.events] == ["Second"]
    with app.state.session_factory() as session:
        assert session.get(Task, item["id"]).external_etag == calendar.events[0].etag


def test_notices_are_bounded(app):
    from collections import deque

    from sdk_example import tasks_wiring

    log = tasks_wiring.notices(app)
    assert isinstance(log, deque) and log.maxlen == 500
    for number in range(600):
        log.append({"n": number})
    assert len(log) == 500 and log[0] == {"n": 100}
