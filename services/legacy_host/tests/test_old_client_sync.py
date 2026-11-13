"""An old client in the field: the legacy data keys over `POST /sync/upload`, recorded as fixtures and replayed."""

from __future__ import annotations

from datetime import datetime

import pytest
from sync_util import load, raw, replay, upload

from legacy_host.models import Task

CLOCK = datetime(2026, 11, 8, 10, 0)


@pytest.fixture
def replayed(app, client):
    """The recorded session, replayed once: the answers per request."""
    return replay(client, load("upload_old_client.json"))


def row(app, task_id):
    with app.state.session_factory() as session:
        return session.get(Task, task_id)


def test_every_verdict_is_the_recorded_one(replayed):
    assert [{"results": answer["results"]} for answer in replayed] == load("upload_old_client_expected.json")["answers"]


def test_server_owned_values_in_the_payload_are_ignored(app, replayed):
    t1 = row(app, "t-1")
    assert (t1.owner_user_id, t1.created_by) == ("u-owner", "u-owner")  # the payload named u-stranger, then u-editor
    assert t1.created_at == CLOCK  # the payload said 2020-01-02
    assert t1.completed_at is None and t1.completed_by is None  # reopened; the payload's values were never read
    assert t1.source == "old_client"  # `source` is device-writable on create (the lib's FIELDS)


def test_unknown_keys_are_ignored_and_known_ones_stored(app, replayed):
    t1 = row(app, "t-1")
    assert (t1.title, t1.notes, t1.due_date.isoformat(), t1.due_time) == ("Call the client back", "bring docs",
                                                                          "2026-11-20", "09:30")
    assert not hasattr(t1, "bogus") and not hasattr(t1, "legacy_flag")


def test_blanks_are_stored_null(app, replayed):
    t1 = row(app, "t-1")
    assert t1.assigned_user_id is None and t1.case_ref is None and t1.client_ref == "cl-1"
    assert raw(app, "t-3", "client_ref", "case_ref") == (None, "ca-1")  # the owner's `client_ref: ""` cleared it


def test_legacy_flag_lands_in_the_legacy_column_as_a_boolean(app, replayed):
    assert raw(app, "t-1", "sync_to_calendar") == (1,) and row(app, "t-1").mirror_enabled is True
    assert raw(app, "t-2", "sync_to_calendar") == (0,) and row(app, "t-2").mirror_enabled is False
    assert raw(app, "t-2", "calendar_event_id") == (None,)  # a task off the calendar has no event


def test_the_owned_task_was_mirrored_once_into_the_legacy_pointer_columns(app, replayed):
    event_id, event_user = raw(app, "t-1", "calendar_event_id", "calendar_event_user_id")
    assert event_user == "u-owner" and event_id == app.state.calendar.events[0].id
    assert len(app.state.calendar.events) == 1  # three queued passes, one event


def test_the_assignee_cannot_relink_but_can_resend_the_same_link(app, replayed):
    results = replayed[1]["results"]
    assert results[0]["code"] == "forbidden" and results[0]["message"] == "not_task_owner"
    t3 = row(app, "t-3")
    assert t3.case_ref == "ca-1" and t3.title == "Review contract v2"  # the refusal wrote nothing; the resend did


def test_a_stranger_is_refused_and_nothing_is_written(app, replayed):
    assert replayed[3]["results"][0]["code"] == "forbidden"
    assert row(app, "t-1").title == "Call the client back"


def test_unreadable_hint_and_blank_numbers_do_not_reject_a_put(app, replayed):
    t4 = row(app, "t-4")
    assert t4 is not None and t4.title == "Unreadable hint" and t4.priority is None
    assert t4.due_at is not None  # the server computed it; the garbage hint was dropped
    t5 = row(app, "t-5")
    assert t5 is not None and t5.priority == 2 and t5.due_at is None


def test_a_closing_op_does_not_read_the_payload_it_ignores(app, replayed):
    t4 = row(app, "t-4")
    assert t4.status == "done" and t4.completed_at == CLOCK  # the server clock, not "not a date"


@pytest.mark.parametrize(("sent", "stored"), [(1, True), (0, False), ("1", True), ("0", False), (True, True),
                                              (False, False), ("false", False), ("true", True)])
def test_the_lib_key_takes_any_boolean_shape_an_old_client_might_send(app, client, sent, stored):
    body = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-b",
                     "data": {"title": "Flag", "mirror_enabled": sent}}]}
    assert upload(client, "u-owner", body).json()["results"] == [{"seq": 0, "status": "ok"}]
    assert row(app, "t-b").mirror_enabled is stored
    assert raw(app, "t-b", "sync_to_calendar") == (int(stored),)


@pytest.mark.parametrize("key", ["sync_to_calendar", "mirror_enabled"])
@pytest.mark.parametrize(("sent", "stored"), [(0, False), ("0", False), (1, True), ("1", True)])
def test_a_patch_flag_in_either_key_is_stored_as_a_boolean(app, client, key, sent, stored):
    start = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-p", "data": {"title": "P"}}]}
    upload(client, "u-owner", start)
    body = {"ops": [{"seq": 0, "op": "patch", "table": "tasks", "id": "t-p", "data": {key: sent}}]}
    assert upload(client, "u-owner", body).json()["results"] == [{"seq": 0, "status": "ok"}]
    assert row(app, "t-p").mirror_enabled is stored


@pytest.mark.parametrize("sent", [2, "2", 0.5, [], {}])
def test_a_flag_that_is_no_boolean_is_one_invalid_verdict(app, client, sent):
    for key in ("sync_to_calendar", "mirror_enabled"):
        body = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-x", "data": {"title": "Flag", key: sent}}]}
        response = upload(client, "u-owner", body)
        assert response.status_code == 200 and response.json()["results"][0]["code"] == "invalid"


def test_the_legacy_key_wins_nothing_over_the_lib_key(app, client):
    body = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-both",
                     "data": {"title": "Both", "mirror_enabled": 0, "sync_to_calendar": 1}}]}
    upload(client, "u-owner", body)
    assert row(app, "t-both").mirror_enabled is False  # the lib's own key is the more specific


def test_a_null_legacy_flag_on_a_patch_changes_nothing(app, client):
    upload(client, "u-owner", {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-n",
                                        "data": {"title": "N", "sync_to_calendar": 0}}]})
    body = {"ops": [{"seq": 0, "op": "patch", "table": "tasks", "id": "t-n",
                     "data": {"title": "N2", "sync_to_calendar": None}}]}
    assert upload(client, "u-owner", body).json()["results"] == [{"seq": 0, "status": "ok"}]
    assert row(app, "t-n").mirror_enabled is False


def test_a_replayed_put_is_a_success_and_leaves_the_row(app, client):
    body = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-r", "data": {"title": "Once"}}]}
    upload(client, "u-owner", body)
    assert upload(client, "u-owner", body).json()["results"] == [{"seq": 0, "status": "ok"}]


def test_an_id_someone_else_owns_is_a_conflict_verdict(app, client):
    upload(client, "u-owner", {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-o", "data": {"title": "Mine"}}]})
    other = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-o", "data": {"title": "Taken"}}]}
    response = upload(client, "u-stranger", other)
    assert response.status_code == 200 and response.json()["results"][0]["status"] == "rejected"
    assert row(app, "t-o").title == "Mine"


def test_recorded_limit_a_key_beside_data_that_the_envelope_does_not_know_refuses_the_whole_request(app, client):
    body = {"ops": [{"seq": 0, "op": "put", "table": "tasks", "id": "t-z", "data": {"title": "Z"}, "device_ts": 1}]}
    assert upload(client, "u-owner", body).status_code == 422  # extra="forbid" on the envelope; keys inside `data` are free
    assert upload(client, "u-owner", {"ops": []}).status_code == 200
