"""Trait 2 (REST half): the app's own columns `client_ref` and `case_ref`, stored by the lib through `host_columns`
and governed by `rules.prepare`: only the owner or an admin relinks."""

import pytest
from conftest import as_user

from legacy_host.models import Task

OWNER, EDITOR, ADMIN, STRANGER = (as_user(u) for u in ("u-owner", "u-editor", "u-admin", "u-stranger"))


@pytest.fixture
def shared(client):
    """An owner's task assigned to the editor, linked to client 1 only."""
    r = client.post("/tasks", json={"id": "t-1", "title": "Shared", "assigned_user_id": "u-editor",
                                    "client_ref": "cl-1"}, headers=OWNER)
    assert r.status_code == 201, r.text
    return client


def stored(session, task_id="t-1"):
    session.expire_all()
    row = session.get(Task, task_id)
    values = row.title, row.client_ref, row.case_ref
    session.rollback()  # end the read transaction: SQLite would lock out the app's next write
    return values


def test_create_stores_the_app_columns(client, session):
    r = client.post("/tasks", json={"id": "t-1", "title": "A", "client_ref": "cl-2", "case_ref": "ca-2"}, headers=OWNER)
    assert r.status_code == 201
    assert (r.json()["client_ref"], r.json()["case_ref"]) == ("cl-2", "ca-2")
    assert stored(session) == ("A", "cl-2", "ca-2")


def test_owner_relinks(shared, session):
    r = shared.put("/tasks/t-1", json={"client_ref": "cl-2"}, headers=OWNER)
    assert r.status_code == 200 and r.json()["client_name"] == "Other Test Co"
    assert stored(session)[1] == "cl-2"


def test_assignee_edits_the_title(shared, session):
    r = shared.put("/tasks/t-1", json={"title": "Renamed"}, headers=EDITOR)
    assert r.status_code == 200 and stored(session) == ("Renamed", "cl-1", None)


def test_assignee_cannot_relink_and_nothing_is_written(shared, session):
    r = shared.put("/tasks/t-1", json={"title": "Sneaky", "client_ref": "cl-2"}, headers=EDITOR)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_task_owner" and r.json()["detail"]["error_code"] == "NOT_TASK_OWNER"
    assert stored(session) == ("Shared", "cl-1", None)  # the title in the same body was not written either


def test_assignee_cannot_link_a_case(shared, session):
    assert shared.put("/tasks/t-1", json={"case_ref": "ca-1"}, headers=EDITOR).status_code == 403
    assert stored(session)[2] is None


def test_assignee_resending_the_unchanged_link_is_allowed(shared, session):
    r = shared.put("/tasks/t-1", json={"title": "Same link", "client_ref": "cl-1"}, headers=EDITOR)
    assert r.status_code == 200 and stored(session) == ("Same link", "cl-1", None)


def test_assignee_resending_a_blank_for_an_empty_link_is_allowed(shared):
    assert shared.put("/tasks/t-1", json={"case_ref": ""}, headers=EDITOR).status_code == 200


def test_assignee_clearing_a_link_is_a_relink(shared, session):
    assert shared.put("/tasks/t-1", json={"client_ref": None}, headers=EDITOR).status_code == 403
    assert stored(session)[1] == "cl-1"


def test_admin_relinks_a_task_they_do_not_own(shared, session):
    r = shared.put("/tasks/t-1", json={"client_ref": "cl-2", "case_ref": "ca-2"}, headers=ADMIN)
    assert r.status_code == 200 and stored(session) == ("Shared", "cl-2", "ca-2")


def test_blank_strings_are_stored_as_null(client, session):
    client.post("/tasks", json={"id": "t-1", "title": "A", "client_ref": "  ", "case_ref": ""}, headers=OWNER)
    assert stored(session) == ("A", None, None)
    client.put("/tasks/t-1", json={"client_ref": "cl-1"}, headers=OWNER)
    client.put("/tasks/t-1", json={"client_ref": ""}, headers=OWNER)
    assert stored(session)[1] is None


def test_a_case_fills_its_client(client, session):
    r = client.post("/tasks", json={"id": "t-1", "title": "A", "case_ref": "ca-2"}, headers=OWNER)
    assert (r.json()["client_ref"], r.json()["case_label"], r.json()["client_name"]) == (
        "cl-2", "Case Two", "Other Test Co")
    client.put("/tasks/t-1", json={"case_ref": "ca-1"}, headers=OWNER)
    assert stored(session) == ("A", "cl-1", "ca-1")


def test_an_explicit_client_is_kept_beside_a_case(client, session):
    client.post("/tasks", json={"id": "t-1", "title": "A", "case_ref": "ca-2", "client_ref": "cl-1"}, headers=OWNER)
    assert stored(session) == ("A", "cl-1", "ca-2")


def test_stranger_cannot_read_or_write(shared, session):
    assert shared.get("/tasks/t-1", headers=STRANGER).status_code == 403
    assert shared.put("/tasks/t-1", json={"title": "x"}, headers=STRANGER).status_code == 403
    assert shared.put("/tasks/t-1", json={"client_ref": "cl-2"}, headers=STRANGER).status_code == 403
    assert stored(session) == ("Shared", "cl-1", None)


def test_missing_task_is_404(client):
    r = client.put("/tasks/nope", json={"title": "x"}, headers=OWNER)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "task_not_found"


def test_app_columns_ride_along_with_every_other_field(client, session):
    r = client.post("/tasks", json={"id": "t-1", "title": "A", "due_date": "2026-11-09", "priority": 3,
                                    "client_ref": "cl-1"}, headers=OWNER)
    assert r.status_code == 201 and r.json()["priority"] == 3 and r.json()["client_ref"] == "cl-1"
