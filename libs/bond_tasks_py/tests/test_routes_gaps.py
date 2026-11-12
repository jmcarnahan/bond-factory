"""``make_tasks_router``: mount order, the ``error_map`` contract and the hook and guard paths that were untested."""

import pytest
from conftest import NOW, LinkIndex, Task, UserSettings
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from test_routes import build, mk

from bond_tasks_py.routes import make_tasks_router


def test_app_static_route_registered_first_wins(factory):
    app = FastAPI()

    @app.get("/tasks/export")
    def export() -> dict:
        return {"export": True}

    app.include_router(_router(factory))
    c = TestClient(app)
    assert c.get("/tasks/export").json() == {"export": True}
    app2 = FastAPI()  # the other order: the id route swallows it
    app2.include_router(_router(factory))

    @app2.get("/tasks/export")
    def export2() -> dict:
        return {"export": True}

    r = TestClient(app2).get("/tasks/export")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "task_not_found"


def _router(factory, **kw):
    from contextlib import contextmanager

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

    args = {"task_model": Task, "settings_model": UserSettings, "link_index_model": LinkIndex, "session_scope": scope,
            "user_dep": user, "now": lambda: NOW, "tz": "UTC"}
    args.update(kw)
    return make_tasks_router(**args)


@pytest.mark.parametrize("bad", [None, 418, (418,), ("418", {}), (True, {}), (418, {}, 1), [418, {}]])
def test_error_map_bad_return_is_a_typeerror_naming_error_map(factory, bad):
    c = build(factory, error_map=lambda e: bad)
    with pytest.raises(TypeError, match="error_map"):
        c.get("/tasks/nope")


def test_error_map_that_raises_is_a_typeerror_naming_error_map(factory):
    def boom(exc):
        raise KeyError("x")

    c = build(factory, error_map=boom)
    with pytest.raises(TypeError, match="error_map raised KeyError"):
        c.get("/tasks/nope")


def test_update_after_write_raise_rolls_back_and_queues_nothing(factory):
    calls = []

    def boom(session, task, now, before):
        raise RuntimeError("hook")

    ok = build(factory)
    mk(ok, id="r1", title="Before")
    c = build(factory, after_write=boom, after_commit=lambda bg, t: calls.append(t.id))
    with pytest.raises(RuntimeError):
        c.put("/tasks/r1", json={"title": "After", "priority": 3})
    assert calls == []
    got = ok.get("/tasks/r1").json()
    assert got["title"] == "Before" and got["priority"] is None and got["status"] == "open"
    with pytest.raises(RuntimeError):
        c.post("/tasks/r1/complete")
    assert ok.get("/tasks/r1").json()["status"] == "open" and calls == []


def test_after_delete_commit_gets_the_mirror_pointer(factory):
    pointers = []
    c = build(factory, after_delete_commit=lambda bg, p: pointers.append(p))
    mk(c, id="m1")
    with factory() as s:
        t = s.get(Task, "m1")
        t.external_event_id, t.external_provider, t.external_account_user_id = "ev1", "google", "u1"
        s.commit()
    assert c.delete("/tasks/m1").status_code == 204
    assert len(pointers) == 1 and pointers[0].event_id == "ev1" and pointers[0].provider == "google"
    assert pointers[0].user_id == "u1"


def test_on_recomputed_called_when_a_settings_change_moves_a_due_instant(factory):
    seen = []
    c = build(factory, on_recomputed=lambda s, task, old, now: seen.append((task.id, old, now)))
    mk(c, id="d1", due_date="2026-11-20")
    old = c.get("/tasks/d1").json()["due_at"]
    assert c.put("/tasks/settings", json={"end_of_day": "18:30"}).status_code == 200
    assert len(seen) == 1 and seen[0][0] == "d1" and seen[0][2] == NOW and seen[0][1] is not None
    assert c.get("/tasks/d1").json()["due_at"] != old
    seen.clear()
    c.put("/tasks/settings", json={"lead_minutes": 45})  # the instant does not move
    assert seen == []


def test_write_dep_guards_delete_and_checklist_tick(factory):
    def need_key(x_key: str | None = Header(None)):
        if x_key != "ok":
            raise HTTPException(403, detail="nope")

    c = build(factory, write_dep=need_key)
    key = {"x-key": "ok"}
    t = c.post("/tasks", json={"title": "T", "id": "g1", "checklist": [{"id": "i1", "text": "a"}]}, headers=key).json()
    assert t["id"] == "g1"
    assert c.delete("/tasks/g1").status_code == 403
    assert c.put("/tasks/g1/checklist/i1", json={"done": True}).status_code == 403
    assert c.get("/tasks/g1").json()["checklist"][0]["done_at"] is None
    assert c.put("/tasks/g1/checklist/i1", json={"done": True}, headers=key).status_code == 200
    assert c.delete("/tasks/g1", headers=key).status_code == 204


def test_body_precheck_runs_on_update(factory):
    c = build(factory)
    mk(c, id="p1")
    for bad in (True, 9, 0):
        r = c.put("/tasks/p1", json={"priority": bad})
        assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_priority", bad
    r = c.put("/tasks/p1", json={"time_zone": "Nowhere/Land"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_time_zone"
    assert c.get("/tasks/p1").json()["priority"] is None


def test_after_write_not_called_on_checklist_tick(factory):
    calls = []
    c = build(factory, after_write=lambda s, t, now, before: calls.append(t.id))
    c.post("/tasks", json={"title": "T", "id": "k1", "checklist": [{"id": "i1", "text": "a"}]})
    assert calls == ["k1"]
    assert c.put("/tasks/k1/checklist/i1", json={"done": True}).status_code == 200
    assert calls == ["k1"]
