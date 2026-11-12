"""``make_tasks_router`` through FastAPI's TestClient on SQLite."""

import subprocess
import sys
from contextlib import contextmanager

import pytest
from conftest import NOW, LinkIndex, Task, UserSettings
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from bond_tasks_py import UserPrefs, serialize
from bond_tasks_py.routes import make_tasks_router


def build(factory, **kw):
    @contextmanager
    def scope():
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def user(x_user: str = Header("u1")):
        return x_user

    app = FastAPI()
    args = {"task_model": Task, "settings_model": UserSettings, "link_index_model": LinkIndex, "session_scope": scope,
            "user_dep": user, "now": lambda: NOW, "tz": "UTC"}
    args.update(kw)
    app.include_router(make_tasks_router(**args))
    return TestClient(app)


@pytest.fixture
def client(factory):
    return build(factory)


def mk(client, user="u1", **body):
    r = client.post("/tasks", json={"title": "T", **body}, headers={"x-user": user})
    assert r.status_code == 201, r.text
    return r.json()


def test_crud_and_status_changes(client):
    t = mk(client, due_date="2026-11-08", id="a1")
    assert list(t)[:3] == ["id", "title", "notes"] and len(t) == len(serialize.ITEM_KEYS)
    assert client.get("/tasks/a1").json()["id"] == "a1"
    assert client.put("/tasks/a1", json={"title": "New"}).json()["title"] == "New"
    for name, status in (("complete", "done"), ("reopen", "open"), ("cancel", "cancelled")):
        assert client.post(f"/tasks/a1/{name}").json()["status"] == status
    body = client.get("/tasks", params={"status": "all"}).json()
    assert body["total"] == 1 and body["limit"] == 25 and body["offset"] == 0
    assert client.get("/tasks/summary").json()["overdue"] == 0
    assert set(client.get("/tasks/today").json()) == {"overdue", "today", "undated", "done_today", "counts"}
    assert client.delete("/tasks/a1").status_code == 204
    r = client.get("/tasks/a1")
    assert r.status_code == 404 and r.json() == {"detail": {"code": "task_not_found", "message": "Task not found."}}


def test_checklist_tick(client):
    t = mk(client, checklist=[{"text": "x"}])
    item_id = t["checklist"][0]["id"]
    r = client.put(f"/tasks/{t['id']}/checklist/{item_id}", json={"done": True})
    assert r.json()["checklist"][0]["done_at"] is not None


def test_body_codes_and_settings(client):
    r = client.post("/tasks", json={"title": "T", "priority": 9})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_priority"
    r = client.post("/tasks", json={"title": "T", "time_zone": "Nowhere/Land"})
    assert r.json()["detail"]["code"] == "invalid_time_zone"
    got = client.get("/tasks/settings").json()
    assert got["overridden"] == [] and got["end_of_day"] == "17:00"
    put = client.put("/tasks/settings", json={"end_of_day": "18:30"}).json()
    assert put["end_of_day"] == "18:30" and put["overridden"] == ["end_of_day"]
    assert client.put("/tasks/settings", json={"end_of_day": None}).json()["overridden"] == []


def test_settings_routes_absent_without_settings_model(factory):
    c = build(factory, settings_model=None)
    assert c.get("/tasks/settings").status_code == 404  # read as a task id
    assert c.put("/tasks/settings", json={}).status_code == 404


def test_defaults_apply(factory):
    c = build(factory, defaults=UserPrefs(end_of_day=__import__("datetime").time(16, 0)))
    assert c.get("/tasks/settings").json()["end_of_day"] == "16:00"


def test_error_map_shapes_body(factory):
    c = build(factory, error_map=lambda e: (418, {"error": e.code}))
    r = c.get("/tasks/nope")
    assert r.status_code == 418 and r.json() == {"error": "task_not_found"}


def test_item_extras_never_override(factory):
    c = build(factory, item_extras=lambda t: {"id": "hacked", "shout": t.title.upper()})
    t = mk(c, id="e1")
    assert t["id"] == "e1" and t["shout"] == "T"
    assert list(t)[-1] == "shout"


def test_extra_where_filters_and_counts(factory):
    c = build(factory, extra_where_for=lambda request, uid: [Task.title == request.headers.get("x-want", "T")])
    mk(c, title="T")
    mk(c, title="Other")
    body = c.get("/tasks", headers={"x-want": "Other"}).json()
    assert body["total"] == 1 and body["items"][0]["title"] == "Other"
    assert c.get("/tasks").json()["total"] == 1


def test_read_all_dep(factory):
    seen = []

    def deny(request):
        seen.append(1)
        raise HTTPException(403, detail="no")

    c = build(factory)
    mk(c, user="u2", id="theirs")
    assert c.get("/tasks", params={"scope": "all"}).status_code == 403  # no read_all_dep: refused
    assert c.get("/tasks/theirs").status_code == 403  # nor someone else's task
    c2 = build(factory, read_all_dep=lambda request: None)
    assert c2.get("/tasks", params={"scope": "all"}).json()["total"] == 1
    assert c2.get("/tasks/theirs").status_code == 200
    c3 = build(factory, read_all_dep=deny)
    assert c3.get("/tasks/theirs").status_code == 403 and seen


def test_write_dep_guards_writes_only(factory):
    def need_key(x_key: str | None = Header(None)):
        if x_key != "ok":
            raise HTTPException(403, detail="nope")

    c = build(factory, write_dep=need_key)
    assert c.post("/tasks", json={"title": "T"}).status_code == 403
    assert c.get("/tasks").status_code == 200
    assert c.post("/tasks", json={"title": "T"}, headers={"x-key": "ok"}).status_code == 201


def test_prepare_refusal(factory):
    from bond_tasks_py import TaskError

    def prepare(session, task, actor, extras):
        raise TaskError("task_closed", "Closed.", 403)

    c = build(factory, prepare=prepare)
    r = c.post("/tasks", json={"title": "T"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "task_closed"
    assert c.get("/tasks", params={"status": "all"}).json()["total"] == 0  # nothing written


def test_hooks(factory):
    calls = []
    c = build(
        factory, snapshot=lambda s, tid: ("snap", tid),
        after_write=lambda s, t, now, before: calls.append(("w", t.id, before)),
        after_delete=lambda s, tid, now: calls.append(("d", tid)),
        after_commit=lambda bg, t: calls.append(("c", t.id)),
        after_delete_commit=lambda bg, p: calls.append(("dc", p)))
    t = mk(c, id="h1")
    c.put("/tasks/h1", json={"title": "x"})
    c.post("/tasks/h1/complete")
    c.delete("/tasks/h1")
    assert ("w", "h1", None) in calls and ("w", "h1", ("snap", "h1")) in calls
    assert ("d", "h1") in calls and ("c", t["id"]) in calls
    assert not any(x[0] == "dc" for x in calls)  # no mirror pointer: nothing to queue


def test_names_labels_zone_for(factory):
    c = build(factory, names=lambda s, ids: {i: f"N-{i}" for i in ids},
              labels=lambda s, links: {(link["kind"], link["id"]): "Fresh" for link in links},
              zone_for=lambda uid: "America/Denver", user_exists=lambda s, uid: True)
    t = mk(c, links=[{"kind": "contact", "id": "c1", "label": "Old"}], due_date="2026-11-08")
    assert t["owner_name"] == "N-u1" and t["links"][0]["label"] == "Fresh"
    assert c.get("/tasks/today").status_code == 200


def test_importing_package_does_not_import_fastapi():
    code = "import bond_tasks_py, sys; assert 'fastapi' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_task_item_extra_and_extras(factory):
    from datetime import date

    from bond_tasks_py import TaskCreate, service, task_item, task_items

    with factory() as session:
        task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                              data=TaskCreate(title="A"), now=NOW)
        base = task_item(task, today=date(2026, 11, 8), now=NOW)
        out = task_item(task, today=date(2026, 11, 8), now=NOW, extra={"id": "x", "more": 1})
        assert out["id"] == task.id and out["more"] == 1 and list(out)[:-1] == list(base)
        many = task_items([task], today=date(2026, 11, 8), now=NOW, extras=lambda t: {"title": "no", "n": t.id})
        assert many[0]["title"] == "A" and many[0]["n"] == task.id
