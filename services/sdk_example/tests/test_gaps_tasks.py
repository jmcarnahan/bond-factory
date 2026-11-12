"""Task routes and wiring that use the adoption-gap seams: read-time labels, status filters, `prepare` on both paths,
the notice owner check, the mirror `draft_for`, and the grant router's redirect mode."""

import asyncio

import pytest
from bond_notify_py import get_owned
from bond_storage import make_download_router
from bond_sync_py import Ctx, UploadRequest, upload
from connections_util import connect, headers
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
from signin_util import ORIGIN
from tasks_util import code, grant, make
from todo_util import grant_write, inbox, sweep, timed

from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID
from sdk_example.models.grants import DownloadGrant
from sdk_example.models.tasks import Task
from sdk_example.routes import notices as notices_routes
from sdk_example.routes.storage import _load_document
from sdk_example.routes.sync import build_host

SAM = {"kind": "contact", "id": "c-sam-rivera", "label": "Sam (old label)"}


@pytest.fixture
def h(client):
    return headers(client)


def sync_one(app, user, *ops):
    body = UploadRequest.model_validate({"transaction_id": 1, "ops": list(ops)})
    return upload(app.state.session_factory, build_host(app), Ctx(user=user), body).wire()["results"]


# --- 3d: link labels at read time --------------------------------------------------------------------------------


def test_a_renamed_contact_shows_its_new_label_and_the_stored_one_is_left_alone(client, app, h):
    task = make(client, h, links=[SAM])
    assert task["links"][0]["label"] == "Sam Rivera"  # the directory's label, not the one the client sent
    app.state.contacts.contacts["c-sam-rivera"] = "Samuel Rivera"
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["links"][0]["label"] == "Samuel Rivera"
    assert client.get("/tasks", headers=h).json()["items"][0]["links"][0]["label"] == "Samuel Rivera"
    with app.state.session_factory() as session:
        assert session.get(Task, task["id"]).links[0]["label"] == "Sam (old label)"


def test_a_link_the_directory_does_not_know_keeps_its_stored_label(client, h):
    gone = {"kind": "contact", "id": "c-removed", "label": "Removed Person"}
    assert make(client, h, links=[gone])["links"][0]["label"] == "Removed Person"


# --- 3c: status filters ------------------------------------------------------------------------------------------


def test_status_cancelled_and_active_filter_the_list(client, h):
    open_task, done_task, dropped = (make(client, h, title=t) for t in ("Open", "Done", "Dropped"))
    client.post(f"/tasks/{done_task['id']}/complete", headers=h)
    client.post(f"/tasks/{dropped['id']}/cancel", headers=h)

    def titles(status):
        reply = client.get("/tasks", params={"status": status}, headers=h)
        assert reply.status_code == 200
        return sorted(t["title"] for t in reply.json()["items"])

    assert titles("cancelled") == ["Dropped"]
    assert titles("active") == ["Done", "Open"]
    assert titles("all") == ["Done", "Dropped", "Open"]
    assert titles("open") == ["Open"]
    assert client.get("/tasks", params={"status": "bogus"}, headers=h).status_code == 422
    assert open_task["status"] == "open"


# --- 3a: prepare on both paths -----------------------------------------------------------------------------------


@pytest.fixture
def shared_done(client, app, h):
    """A done task owned by the demo user and assigned to the viewer, who may write."""
    grant(app, VIEWER_USER_ID)
    task = make(client, h, title="Shared", assigned_user_id=VIEWER_USER_ID)
    assert client.post(f"/tasks/{task['id']}/complete", headers=h).status_code == 200
    return task


def test_prepare_refuses_an_assignee_editing_a_closed_task_over_rest(client, h, shared_done):
    other = headers(client, VIEWER_USER_ID)
    refused = client.put(f"/tasks/{shared_done['id']}", json={"title": "Mine now"}, headers=other)
    assert refused.status_code == 403 and code(refused) == "task_closed"
    assert client.get(f"/tasks/{shared_done['id']}", headers=h).json()["title"] == "Shared"
    assert client.put(f"/tasks/{shared_done['id']}", json={"title": "Owner edit"}, headers=h).status_code == 200


def test_prepare_lets_an_assignee_edit_while_the_task_is_open(client, app, h):
    grant(app, VIEWER_USER_ID)
    task = make(client, h, title="Open one", assigned_user_id=VIEWER_USER_ID)
    other = headers(client, VIEWER_USER_ID)
    assert client.put(f"/tasks/{task['id']}", json={"title": "Edited"}, headers=other).status_code == 200


def test_prepare_refuses_the_same_edit_over_sync(app, shared_done):
    refused = sync_one(app, VIEWER_USER_ID, {"seq": 0, "op": "patch", "table": "tasks", "id": shared_done["id"],
                                             "action": None, "data": {"title": "Mine now"}})
    assert [(r["status"], r["code"], r["message"]) for r in refused] == [("rejected", "forbidden", "task_closed")]
    with app.state.session_factory() as session:
        assert session.get(Task, shared_done["id"]).title == "Shared"
    allowed = sync_one(app, DEMO_USER_ID, {"seq": 1, "op": "patch", "table": "tasks", "id": shared_done["id"],
                                           "action": None, "data": {"title": "Owner edit"}})
    assert allowed[0]["status"] == "ok"


# --- W4: the act route checks the notice owner first -------------------------------------------------------------


def test_act_asks_get_owned_first_and_a_refusal_changes_nothing(client, app, h, monkeypatch):
    task = timed(client, h)
    sweep(client, h, "2026-11-09T09:30:00Z")
    [notice] = inbox(client, h)
    grant_write(app)
    stranger = headers(client, VIEWER_USER_ID)
    seen = []

    def spy(session, notice_model, user_id, notice_id):
        seen.append((user_id, notice_id))
        return get_owned(session, notice_model, user_id, notice_id)

    monkeypatch.setattr(notices_routes.inbox, "get_owned", spy)
    reply = client.post(f"/notices/{notice['id']}/act", json={"action": "done"}, headers=stranger)
    assert reply.status_code == 403 and code(reply) == "not_notice_owner"
    assert seen == [(VIEWER_USER_ID, notice["id"])]
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["status"] == "open"
    missing = client.post("/notices/nope/act", json={"action": "done"}, headers=h)
    assert missing.status_code == 404 and code(missing) == "notice_not_found"


# --- 2a: the mirror's draft_for names the first link -------------------------------------------------------------


def calendar_of(app):
    return next(iter(app.state.fake_calendars.values()))


def test_the_mirrored_event_body_names_the_first_link_by_its_current_label(client, app, h):
    connect(client, h, "fake-google")
    app.state.contacts.contacts["c-sam-rivera"] = "Samuel Rivera"
    make(client, h, title="Ring", due_date="2026-11-09", notes="Ask about the quote", links=[SAM])
    [event] = calendar_of(app).events
    assert event.body == "Ask about the quote\nLinked: Samuel Rivera"


def test_a_task_with_no_link_keeps_the_plain_body(client, app, h):
    connect(client, h, "fake-google")
    make(client, h, title="Plain", due_date="2026-11-09", notes="Just notes")
    assert calendar_of(app).events[0].body == "Just notes"


def test_the_sync_path_mirrors_with_the_same_draft_for(client, app, h):
    connect(client, h, "fake-google")
    op = {"seq": 0, "op": "put", "table": "tasks", "id": "dev-link", "action": None,
          "data": {"title": "From a phone", "due_date": "2026-11-09", "links": [SAM]}}
    body = UploadRequest.model_validate({"transaction_id": 1, "ops": [op]})
    background = BackgroundTasks()
    upload(app.state.session_factory, build_host(app), Ctx(user=DEMO_USER_ID, background=background), body)
    asyncio.run(background())
    assert calendar_of(app).events[0].body == "Linked: Sam Rivera"


# --- 9g: the grant router in redirect mode over the local backend streams -----------------------------------------


def test_redirect_delivery_over_the_local_backend_falls_back_to_streaming(app):
    owner = TestClient(app, headers=ORIGIN)
    assert owner.post("/auth/demo", json={"user_id": DEMO_USER_ID}).status_code == 200
    document = owner.post("/documents", files={"file": ("r.pdf", b"%PDF-1.4 bytes", "application/pdf")}).json()
    link = owner.post(f"/documents/{document['id']}/share", json=None).json()["url"]
    mini = FastAPI()
    mini.include_router(make_download_router(storage=app.state.storage, grant_model=DownloadGrant,
                                             document_loader=_load_document, session_factory=app.state.session_factory,
                                             delivery="redirect", presign_seconds=30))
    answer = TestClient(mini).get(link, follow_redirects=False)
    assert answer.status_code == 200 and answer.content == b"%PDF-1.4 bytes"  # no 302: the local backend cannot presign
