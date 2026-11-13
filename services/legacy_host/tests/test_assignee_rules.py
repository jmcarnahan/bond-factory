"""Facts an adopter relies on, pinned: who may reassign a task, what an unchanged assignee is, what a blank assignee
is, and what an old client's patch leaves alone. Through `POST /sync/upload` and the REST route."""

from __future__ import annotations

import pytest
from conftest import as_user
from sqlalchemy import text
from sync_util import upload

OWNER, EDITOR, ADMIN, STRANGER = "u-owner", "u-editor", "u-admin", "u-stranger"


@pytest.fixture
def shared(client):
    """An owner's task assigned to the editor."""
    r = client.post("/tasks", json={"id": "t-1", "title": "Shared", "assigned_user_id": EDITOR}, headers=as_user(OWNER))
    assert r.status_code == 201, r.text
    return client


def assignee(app, task_id="t-1"):
    with app.state.engine.connect() as conn:
        return conn.execute(text("SELECT assigned_user_id FROM tasks WHERE id = :i"), {"i": task_id}).scalar_one()


def sync_patch(client, user, **data):
    response = upload(client, user, {"transaction_id": 1, "ops": [
        {"seq": 0, "op": "patch", "table": "tasks", "id": "t-1", "data": data}]})
    assert response.status_code == 200, response.text
    return response.json()["results"][0]


def rest_put(client, user, **data):
    return client.put("/tasks/t-1", json=data, headers=as_user(user))


# sync

@pytest.mark.parametrize("who", [EDITOR, STRANGER])
def test_sync_reassign_by_neither_owner_nor_admin_is_refused(app, shared, who):
    assert sync_patch(shared, who, assigned_user_id=STRANGER if who == EDITOR else OWNER) == {
        "seq": 0, "status": "rejected", "code": "forbidden", "message": "not_task_owner"}
    assert assignee(app) == EDITOR


@pytest.mark.parametrize("who", [OWNER, ADMIN])
def test_sync_reassign_by_owner_or_admin_works(app, shared, who):
    assert sync_patch(shared, who, assigned_user_id=STRANGER) == {"seq": 0, "status": "ok"}
    assert assignee(app) == STRANGER


def test_sync_the_same_assignee_sent_again_is_not_a_change_even_from_the_editor(app, shared):
    assert sync_patch(shared, EDITOR, assigned_user_id=EDITOR, title="Renamed") == {"seq": 0, "status": "ok"}
    assert assignee(app) == EDITOR


def test_sync_a_blank_assignee_is_null(app, shared):
    assert sync_patch(shared, OWNER, assigned_user_id="") == {"seq": 0, "status": "ok"}
    assert assignee(app) is None


def test_sync_a_blank_assignee_on_an_unassigned_task_is_no_change(app, client):
    client.post("/tasks", json={"id": "t-1", "title": "Solo"}, headers=as_user(OWNER))
    assert sync_patch(client, OWNER, assigned_user_id="") == {"seq": 0, "status": "ok"}
    assert assignee(app) is None


# REST

@pytest.mark.parametrize("who", [EDITOR, STRANGER])
def test_rest_reassign_by_neither_owner_nor_admin_is_refused(app, shared, who):
    r = rest_put(shared, who, assigned_user_id=STRANGER if who == EDITOR else OWNER)
    assert r.status_code == 403, r.text
    assert assignee(app) == EDITOR


@pytest.mark.parametrize("who", [OWNER, ADMIN])
def test_rest_reassign_by_owner_or_admin_works(app, shared, who):
    assert rest_put(shared, who, assigned_user_id=STRANGER).status_code == 200
    assert assignee(app) == STRANGER


def test_rest_the_same_assignee_sent_again_is_ok_from_the_editor(app, shared):
    assert rest_put(shared, EDITOR, assigned_user_id=EDITOR, title="Renamed").status_code == 200
    assert assignee(app) == EDITOR


def test_rest_a_blank_assignee_is_null(app, shared):
    assert rest_put(shared, OWNER, assigned_user_id="").status_code == 200
    assert assignee(app) is None


# an old client's patch

def test_an_old_clients_patch_leaves_the_columns_it_never_uploads(app, client):
    r = client.post("/tasks", json={"id": "t-1", "title": "Rich", "priority": 2, "remind_minutes_before": 15,
                                    "checklist": [{"id": "c1", "text": "one"}],
                                    "links": [{"kind": "client", "id": "cl-1", "label": "Acme Test Co"}]}, headers=as_user(OWNER))
    assert r.status_code == 201, r.text
    cols = "priority, checklist, links, remind_minutes_before"

    def read():
        with app.state.engine.connect() as conn:
            return tuple(conn.execute(text(f"SELECT {cols} FROM tasks WHERE id = 't-1'")).one())

    before = read()
    assert before[0] == 2 and before[3] == 15 and before[1] and before[2]
    # the old build declares only its own columns, so its patch carries only those (and the legacy key)
    assert sync_patch(client, OWNER, title="Renamed", notes="n", sync_to_calendar=0) == {"seq": 0, "status": "ok"}
    assert read() == before
    with app.state.engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM tasks WHERE id = 't-1'")).scalar_one() == "Renamed"
