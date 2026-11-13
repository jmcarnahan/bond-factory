"""Partial ownership of an external record: the person edits the calendar event; the host keeps writing the rest."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sync_util import raw, upload

LEFT = {"location", "categories", "reminder_minutes"}


def put(client, task_id="t-m", **data):
    body = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": task_id,
                     "data": {"title": "Send the quote", "due_date": "2026-11-20", "due_time": "09:30",
                              "sync_to_calendar": 1, **data}}]}
    assert upload(client, "u-owner", body).json()["results"] == [{"seq": 0, "status": "ok"}]


def patch(client, task_id="t-m", **data):
    body = {"ops": [{"seq": 0, "op": "patch", "table": "tasks", "id": task_id, "data": data}]}
    assert upload(client, "u-owner", body).json()["results"] == [{"seq": 0, "status": "ok"}]


def user_edits_event(app):
    """The person, in their own calendar: a room, a category and a 45 minute reminder (the fake keeps no reminder
    field on an event, so it is set as a plain attribute that only a write through the patch could replace)."""
    event = app.state.calendar.events[0]
    event.location, event.categories = "Room 4", ["Blue"]
    event.reminder_minutes = 45
    app.state.calendar._stamp(event)  # a provider-side edit moves the etag; the stored pointer is now stale
    return event


def updates(app):
    return [args for name, args in app.state.calendar.calls if name == "update_event"]


@pytest.fixture
def mirrored(app, client):
    put(client)
    return app


def test_a_dated_task_creates_one_event_and_stores_the_pointer_in_the_legacy_columns(mirrored):
    app = mirrored
    event = app.state.calendar.events[0]
    assert raw(app, "t-m", "calendar_event_id", "calendar_event_user_id") == (event.id, "u-owner")
    assert (event.subject, event.start) == ("Send the quote", datetime(2026, 11, 20, 9, 30, tzinfo=UTC))
    assert [name for name, _ in app.state.calendar.calls] == ["create_event"]
    assert raw(app, "t-m", "mirror_status") == ("mirrored",)


def test_a_title_change_updates_the_subject_and_leaves_what_the_person_set(mirrored, client):
    app = mirrored
    event = user_edits_event(app)
    patch(client, title="Send the revised quote")
    assert event.subject == "Send the revised quote"
    assert (event.location, event.categories, event.reminder_minutes) == ("Room 4", ["Blue"], 45)
    assert len(app.state.calendar.events) == 1 and raw(app, "t-m", "mirror_status") == ("mirrored",)


def test_the_stale_etag_path_rereads_and_still_omits_the_left_fields(mirrored, client):
    app = mirrored
    user_edits_event(app)
    patch(client, title="Send the revised quote")
    assert [name for name, _ in app.state.calendar.calls] == ["create_event", "update_event", "get_event", "update_event"]
    first, second = updates(app)
    assert first[1] == second[1]  # the same patch both times
    assert not set(first[1]) & (LEFT | {"leave"}) and first[1]["subject"] == "Send the revised quote"


def test_the_time_the_host_owns_still_moves_the_event(mirrored, client):
    app = mirrored
    user_edits_event(app)
    patch(client, due_time="14:00")
    event = app.state.calendar.events[0]
    assert event.start == datetime(2026, 11, 20, 14, 0, tzinfo=UTC) and event.location == "Room 4"


def test_the_tasks_own_reminder_change_is_not_propagated_while_the_reminder_is_left(mirrored, client):
    """The recorded trade: a field named in `leave` is the person's, so the task's `remind_minutes_before` cannot move
    the event's reminder after the first push (the task's own notices still follow the task)."""
    app = mirrored
    event = user_edits_event(app)
    patch(client, remind_minutes_before=10)
    assert event.reminder_minutes == 45
    assert all("reminder_minutes" not in args[1] for args in updates(app))


def test_a_deleted_event_is_recreated_with_every_field(mirrored, client):
    app = mirrored
    app.state.calendar.events.clear()  # the person deleted the event in their calendar
    patch(client, title="Send it again")
    event = app.state.calendar.events[0]
    assert event.subject == "Send it again" and len(app.state.calendar.events) == 1
    created = [args for name, args in app.state.calendar.calls if name == "create_event"][-1][0]
    assert created.subject == "Send it again"  # a create owns every field, `leave` included in the draft
    assert raw(app, "t-m", "calendar_event_id") == (event.id,)


def test_without_leave_a_host_overwrites_what_the_person_set(app, client):
    """The control: a draft_for that leaves nothing out (the lib's default) sends every field on every update."""
    app.state.mirror_draft_for = lambda session, task, draft: draft
    put(client)
    event = user_edits_event(app)
    patch(client, title="Send the revised quote")
    assert event.location is None and event.categories == []
    assert {"location", "categories", "reminder_minutes"} <= set(updates(app)[-1][1])
