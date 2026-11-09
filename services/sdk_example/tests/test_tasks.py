"""Tasks routes over a fake-mode app: access, CRUD, validation, filters, summary, checklist."""

import pytest
from bond_tasks_py import ITEM_KEYS
from connections_util import headers
from tasks_util import TODAY, code, grant, make

from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID


@pytest.fixture
def h(client):
    return headers(client)


def test_routes_need_a_session(client):
    assert client.get("/tasks").status_code == 401
    assert client.post("/tasks", json={"title": "x"}).status_code == 401
    assert client.get("/tasks/summary").status_code == 401


def test_a_viewer_can_read_but_not_write(client):
    viewer = headers(client, VIEWER_USER_ID)
    assert client.get("/tasks", headers=viewer).json()["items"] == []
    reply = client.post("/tasks", json={"title": "x"}, headers=viewer)
    assert reply.status_code == 403 and code(reply) == "forbidden"


def test_create_returns_201_and_the_full_item(client, h):
    item = make(client, h, notes="n", due_date="2026-11-09", due_time="09:30", remind_minutes_before=15,
                checklist=[{"text": "one"}, {"text": "two"}], links=[{"kind": "contact", "id": "c1", "label": "C"}])
    assert list(item) == list(ITEM_KEYS)
    assert (item["owner_user_id"], item["owner_name"], item["status"]) == (DEMO_USER_ID, "Demo User", "open")
    assert item["remind_at"] == "2026-11-09T09:15:00Z" and item["overdue"] is False
    assert [c["text"] for c in item["checklist"]] == ["one", "two"] and item["links"][0]["id"] == "c1"


def test_get_and_list_and_not_found(client, h):
    item = make(client, h)
    assert client.get(f"/tasks/{item['id']}", headers=h).json()["id"] == item["id"]
    listed = client.get("/tasks", headers=h).json()
    assert (listed["total"], listed["limit"], listed["offset"]) == (1, 25, 0)
    missing = client.get("/tasks/nope", headers=h)
    assert missing.status_code == 404 and code(missing) == "task_not_found"


def test_update_omitted_unchanged_and_null_clears(client, h):
    item = make(client, h, notes="n", due_date="2026-11-09", due_time="09:00")
    kept = client.put(f"/tasks/{item['id']}", json={"title": "New"}, headers=h).json()
    assert (kept["title"], kept["notes"], kept["due_time"]) == ("New", "n", "09:00")
    cleared = client.put(f"/tasks/{item['id']}", json={"notes": None, "due_date": None}, headers=h).json()
    assert (cleared["notes"], cleared["due_date"], cleared["due_time"]) == (None, None, None)


def test_validation_codes(client, h):
    missing = client.post("/tasks", json={}, headers=h)
    assert missing.status_code == 422 and code(missing) == "title_required"
    assert code(client.post("/tasks", json={"title": "x", "due_time": "09:00"}, headers=h)) == "due_time_requires_date"
    assert code(client.post("/tasks", json={"title": "x", "assigned_user_id": "ghost"}, headers=h)) == "unknown_assignee"
    assert code(client.post("/tasks", json={"title": "x", "due_time": "9am"}, headers=h)) == "validation_error"
    assert code(client.post("/tasks", json={"title": "x", "owner_user_id": "u"}, headers=h)) == "validation_error"


def test_complete_and_reopen(client, h):
    item = make(client, h, due_date="2026-11-01")
    done = client.post(f"/tasks/{item['id']}/complete", headers=h).json()
    assert done["status"] == "done" and done["completed_at"] and done["overdue"] is False
    reopened = client.post(f"/tasks/{item['id']}/reopen", params={"today": TODAY}, headers=h).json()
    assert reopened["status"] == "open" and reopened["completed_at"] is None and reopened["overdue"] is True


def test_delete_is_204_hard_and_owner_only(client, app, h):
    grant(app)
    other = headers(client, VIEWER_USER_ID)
    item = make(client, h, assigned_user_id=VIEWER_USER_ID)
    denied = client.delete(f"/tasks/{item['id']}", headers=other)
    assert denied.status_code == 403 and code(denied) == "not_task_owner"
    gone = client.delete(f"/tasks/{item['id']}", headers=h)
    assert gone.status_code == 204 and gone.content == b""
    assert client.get(f"/tasks/{item['id']}", headers=h).status_code == 404


def test_non_editor_cannot_edit_and_assignee_can(client, app, h):
    grant(app)
    other = headers(client, VIEWER_USER_ID)
    mine = make(client, h)
    refused = client.put(f"/tasks/{mine['id']}", json={"title": "x"}, headers=other)
    assert refused.status_code == 403 and code(refused) == "not_task_editor"
    shared = make(client, h, assigned_user_id=VIEWER_USER_ID)
    assert shared["assignee_name"] == "Viewer User"
    ok = client.put(f"/tasks/{shared['id']}", json={"notes": "by assignee"}, headers=other)
    assert ok.status_code == 200 and ok.json()["notes"] == "by assignee"
    reassign = client.put(f"/tasks/{shared['id']}", json={"assigned_user_id": None}, headers=other)
    assert reassign.status_code == 403 and code(reassign) == "not_task_owner"


def test_client_chosen_id_replay_and_id_taken(client, app, h):
    grant(app)
    first = make(client, h, id="phone-1", title="One")
    replay = client.post("/tasks", json={"id": "phone-1", "title": "Other"}, headers=h)
    assert replay.status_code == 201 and replay.json()["id"] == first["id"] and replay.json()["title"] == "One"
    taken = client.post("/tasks", json={"id": "phone-1", "title": "Mine"}, headers=headers(client, VIEWER_USER_ID))
    assert taken.status_code == 409 and code(taken) == "id_taken"


def test_list_filters(client, h):
    make(client, h, title="late", due_date="2026-11-01")
    make(client, h, title="today", due_date=TODAY)
    make(client, h, title="later", due_date="2026-11-30")
    make(client, h, title="undated")
    done = make(client, h, title="done", due_date=TODAY)
    client.post(f"/tasks/{done['id']}/complete", headers=h)

    def names(**params):
        return [i["title"] for i in client.get("/tasks", params=params, headers=h).json()["items"]]

    assert names() == ["late", "today", "later", "undated"]
    assert names(status="done") == ["done"]
    assert names(status="all")[-1] in ("undated", "done") and len(names(status="all")) == 5
    assert names(no_date="true") == ["undated"]
    assert names(on_or_before=TODAY) == ["late", "today"]
    assert names(on_or_before=TODAY, include_undated="true") == ["late", "today", "undated"]
    assert names(due_from="2026-11-05", due_to="2026-11-10") == ["today"]
    assert client.get("/tasks", params={"limit": 2, "offset": 1}, headers=h).json()["total"] == 4
    assert client.get("/tasks", params={"status": "bogus"}, headers=h).status_code == 422


def test_link_and_owner_filters(client, app, h):
    grant(app)
    grant(app, DEMO_USER_ID, "tasks.write", "tasks.read_all")
    make(client, h, title="a", links=[{"kind": "loan", "id": "L1"}])
    other = headers(client, VIEWER_USER_ID)
    make(client, other, title="b", links=[{"kind": "loan", "id": "L1"}])
    wide = {"scope": "all", "link_kind": "loan", "link_id": "L1"}
    reply = client.get("/tasks", params=wide, headers=h).json()
    assert sorted(i["title"] for i in reply["items"]) == ["a", "b"]
    mine = client.get("/tasks", params={"link_kind": "loan", "link_id": "L1"}, headers=h).json()
    assert [i["title"] for i in mine["items"]] == ["a"]  # a link filter never widens the scope
    reply = client.get("/tasks", params={"scope": "all", "owner_user_id": VIEWER_USER_ID}, headers=h).json()
    assert [i["title"] for i in reply["items"]] == ["b"]


def test_reading_beyond_your_own_tasks_needs_read_all(client, app, h):
    grant(app, DEMO_USER_ID, "tasks.write")
    grant(app)
    viewer = headers(client, VIEWER_USER_ID)
    theirs = make(client, h, title="private")
    refused = client.get("/tasks", params={"scope": "all"}, headers=viewer)
    assert refused.status_code == 403 and code(refused) == "forbidden"
    other = client.get(f"/tasks/{theirs['id']}", headers=viewer)
    assert other.status_code == 403 and code(other) == "forbidden"
    assert client.get("/tasks", params={"link_id": "x"}, headers=viewer).json()["items"] == []
    shared = make(client, h, title="shared", assigned_user_id=VIEWER_USER_ID)
    assert client.get(f"/tasks/{shared['id']}", headers=viewer).status_code == 200  # an assignee may read it
    grant(app, VIEWER_USER_ID, "tasks.write", "tasks.read_all")
    assert client.get(f"/tasks/{theirs['id']}", headers=viewer).status_code == 200
    assert len(client.get("/tasks", params={"scope": "all"}, headers=viewer).json()["items"]) == 2


def test_cancel_is_owner_only_and_so_is_undoing_it(client, app, h):
    grant(app)
    other = headers(client, VIEWER_USER_ID)
    item = make(client, h, assigned_user_id=VIEWER_USER_ID, due_date="2026-11-09")
    denied = client.post(f"/tasks/{item['id']}/cancel", headers=other)
    assert denied.status_code == 403 and code(denied) == "not_task_owner"
    cancelled = client.post(f"/tasks/{item['id']}/cancel", params={"today": TODAY}, headers=h).json()
    assert (cancelled["status"], cancelled["completed_at"]) == ("cancelled", None)
    assert client.get("/tasks", headers=h).json()["items"] == []
    assert client.get("/tasks", params={"status": "all"}, headers=h).json()["total"] == 1
    for path in ("complete", "reopen"):
        refused = client.post(f"/tasks/{item['id']}/{path}", headers=other)
        assert refused.status_code == 403 and code(refused) == "not_task_owner"
    assert client.post(f"/tasks/{item['id']}/reopen", headers=h).json()["status"] == "open"
    assert client.post(f"/tasks/{item['id']}/cancel", headers=h).status_code == 200


def test_nul_bytes_and_null_lists_are_422(client, h):
    item = make(client, h)
    for body in ({"title": "a\u0000b"}, {"notes": "x\u0000"}, {"checklist": [{"text": "a\u0000"}]},
                 {"checklist": None}, {"links": None}, {"remind_minutes_before": None}, {"mirror_enabled": None}):
        reply = client.put(f"/tasks/{item['id']}", json=body, headers=h)
        assert reply.status_code == 422 and code(reply) == "validation_error", body
    assert client.post("/tasks", json={"id": "caf\u00e9", "title": "x"}, headers=h).status_code == 422


def test_summary_counts(client, h):
    make(client, h, due_date="2026-11-01")
    make(client, h, due_date=TODAY)
    make(client, h)
    done = make(client, h, due_date=TODAY)
    client.post(f"/tasks/{done['id']}/complete", headers=h)
    reply = client.get("/tasks/summary", params={"today": TODAY}, headers=h)
    assert reply.json() == {"open": 3, "overdue": 1, "due_today": 1, "no_date": 1}


def test_checklist_tick_and_untick(client, h):
    item = make(client, h, checklist=[{"text": "one"}])
    cid = item["checklist"][0]["id"]
    ticked = client.put(f"/tasks/{item['id']}/checklist/{cid}", json={"done": True}, headers=h).json()
    assert ticked["checklist"][0]["done_at"].endswith("Z")
    unticked = client.put(f"/tasks/{item['id']}/checklist/{cid}", json={"done": False}, headers=h).json()
    assert unticked["checklist"][0]["done_at"] is None
    missing = client.put(f"/tasks/{item['id']}/checklist/zzz", json={"done": True}, headers=h)
    assert missing.status_code == 404 and code(missing) == "checklist_item_not_found"
