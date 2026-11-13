"""Trait 1: the lib attributes live in columns the app named first, and rows that pre-date the modules still work."""

from datetime import datetime

import bond_tasks_py as tasks
import pytest
from conftest import as_user
from fastapi.testclient import TestClient
from legacy_db import legacy_app, old_task
from sqlalchemy import text

from legacy_host.models import Task

OWNER = as_user("u-owner")
LEGACY_SQL = text("SELECT sync_to_calendar, calendar_event_id, calendar_event_user_id FROM tasks WHERE id = :id")


def test_renamed_attributes_map_to_the_legacy_columns(app, client, session):
    names = {c.name for c in Task.__table__.c}
    assert {"sync_to_calendar", "calendar_event_id", "calendar_event_user_id"} <= names
    assert not names & {"mirror_enabled", "external_event_id", "external_account_user_id"}
    client.post("/tasks", json={"id": "t-1", "title": "A", "mirror_enabled": False}, headers=OWNER)
    assert tuple(session.execute(LEGACY_SQL, {"id": "t-1"}).one()) == (0, None, None)


def test_writing_the_attributes_writes_the_legacy_columns(client, session):
    client.post("/tasks", json={"id": "t-1", "title": "A"}, headers=OWNER)
    task = session.get(Task, "t-1")
    task.mirror_enabled, task.external_event_id, task.external_account_user_id = False, "ev-9", "u-owner"
    session.commit()
    assert tuple(session.execute(LEGACY_SQL, {"id": "t-1"}).one()) == (0, "ev-9", "u-owner")


def test_reading_the_attributes_reads_the_legacy_columns(client, session):
    client.post("/tasks", json={"id": "t-1", "title": "A"}, headers=OWNER)
    session.execute(text("UPDATE tasks SET sync_to_calendar = 0, calendar_event_id = 'raw-1' WHERE id = 't-1'"))
    session.commit()
    task = session.get(Task, "t-1")
    assert (task.mirror_enabled, task.external_event_id) == (False, "raw-1")
    item = client.get("/tasks/t-1", headers=OWNER).json()
    assert (item["mirror_enabled"], item["external_event_id"]) == (False, "raw-1")


@pytest.fixture
def old(tmp_path):
    """A host started on a database whose rows were written by the old app, before the mixin columns existed."""
    def fill(connection):
        old_task(connection, "old-open", title="Call back", due_date="2026-11-09", due_time="14:00", sync=0,
                 event_id="ev-1")
        old_task(connection, "old-dateonly", title="Send form", due_date="2026-11-07")
        old_task(connection, "old-done", title="Filed", status="done")
        old_task(connection, "old-shared", title="Team item", assignee="u-editor")

    app = legacy_app(tmp_path / "old.db", fill)
    return app, TestClient(app)


def test_old_rows_have_null_in_every_added_column(old):
    app, _ = old
    with app.state.session_factory() as session:
        row = session.execute(text(
            "SELECT priority, due_at, checklist, links, remind_minutes_before, mirror_status, external_provider, "
            "external_etag, source FROM tasks WHERE id = 'old-open'")).one()
    assert all(value is None for value in row)


def test_old_rows_list_and_serialise(old):
    _, client = old
    body = client.get("/tasks?status=all", headers=OWNER).json()
    assert body["total"] == 4
    by_id = {item["id"]: item for item in body["items"]}
    item = by_id["old-open"]
    assert (item["checklist"], item["links"], item["source"], item["priority"]) == ([], [], "manual", None)
    assert item["mirror_status"] == "pending" and item["sync_to_calendar"] is False
    assert (item["external_event_id"], item["calendar_event_id"]) == ("ev-1", "ev-1")
    assert by_id["old-dateonly"]["overdue"] is True  # due before the viewer's today, due_at not computed
    assert by_id["old-done"]["status"] == "done"


def test_old_row_updates_and_computes_its_due_instant(old):
    app, client = old
    r = client.put("/tasks/old-open", json={"title": "Call back today", "due_date": "2026-11-10"}, headers=OWNER)
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Call back today" and r.json()["due_at"] is not None
    with app.state.session_factory() as session:
        row = session.get(Task, "old-open")
        assert row.checklist is None and row.remind_minutes_before is None  # untouched columns stay as they were


def test_old_row_edited_by_its_assignee(old):
    _, client = old
    r = client.put("/tasks/old-shared", json={"notes": "seen"}, headers=as_user("u-editor"))
    assert r.status_code == 200 and r.json()["notes"] == "seen"


def test_old_rows_complete_and_reopen(old):
    _, client = old
    done = client.post("/tasks/old-open/complete", headers=OWNER).json()
    assert done["status"] == "done" and done["completed_at"] is not None
    reopened = client.post("/tasks/old-done/reopen", headers=OWNER).json()
    assert reopened["status"] == "open" and reopened["completed_at"] is None


def test_old_rows_in_the_day_view_and_the_summary(old):
    app, _ = old
    now = datetime(2026, 11, 8, 10, 0)
    with app.state.session_factory() as session:
        found = tasks.today(session, task_model=Task, user_id="u-owner", now=now, viewer_zone="UTC")
        counts = tasks.summary(session, task_model=Task, user_id="u-owner", now=now, viewer_zone="UTC")
    assert {t.id for t in found.overdue} == {"old-dateonly"}
    assert counts["open"] == 3 and counts["no_date"] == 1


def _stage_times(app):
    with app.state.session_factory() as session:
        row = session.get(Task, "old-open")
        row.due_at = tasks.compute_due_at(row.due_date, row.due_time, writer_zone="UTC",
                                          responsible_prefs=tasks.UserPrefs(), app_tz="UTC")
        return tasks.stage_times(row, tasks.UserPrefs(), "UTC", datetime(2026, 11, 8, 10, 0))


def test_an_old_row_with_a_null_reminder_follows_the_default(old):
    """The column was added after rows existed, so it is NULL: the lib reads NULL as `USE_DEFAULT_REMINDER` (stages,
    mirror draft and item), so stage times equal those of a row whose reminder is the default (-3)."""
    app = old[0]
    with_null = _stage_times(app)
    with app.state.session_factory() as session:
        session.execute(text("UPDATE tasks SET remind_minutes_before = -3 WHERE remind_minutes_before IS NULL"))
        session.commit()
    assert with_null and with_null == _stage_times(app)


def test_old_row_stage_times_after_the_reminder_backfill(old):
    app, _ = old
    with app.state.session_factory() as session:
        session.execute(text("UPDATE tasks SET remind_minutes_before = -3 WHERE remind_minutes_before IS NULL"))
        session.commit()
    assert _stage_times(app)
