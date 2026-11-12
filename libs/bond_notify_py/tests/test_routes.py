"""``make_notices_router`` through FastAPI's TestClient on SQLite."""

from contextlib import contextmanager
from datetime import datetime

import pytest
from conftest import Base, Notice
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from bond_notify_py.routes import make_notices_router

NOW = datetime(2026, 11, 8, 12, 0, 0)


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


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
    app.include_router(make_notices_router(notice_model=Notice, session_scope=scope, user_dep=user,
                                           now=lambda: NOW, **kw))
    return TestClient(app)


def seed(factory, nid, user="u1", source="t1"):
    with factory() as s:
        s.add(Notice(id=nid, user_id=user, kind="task", title="T", body="B", data={"task_id": source},
                     source_id=source, created_at=NOW))
        s.commit()


def test_list_read_dismiss_read_all(factory):
    c = build(factory)
    for i in ("n1", "n2", "n3"):
        seed(factory, i)
    body = c.get("/notices").json()
    assert body["unread_count"] == 3 and len(body["items"]) == 3 and body["next_cursor"] is None
    assert c.post("/notices/n1/read").json()["read_at"] is not None
    assert c.post("/notices/n2/dismiss").json()["dismissed_at"] is not None
    assert c.get("/notices", params={"unread": True}).json()["unread_count"] == 1
    assert c.post("/notices/read-all").json() == {"unread_count": 0}
    r = c.post("/notices/zz/read")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "notice_not_found"


def test_another_users_notice_is_403(factory):
    c = build(factory)
    seed(factory, "n1", user="u2")
    r = c.post("/notices/n1/dismiss")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_notice_owner"


def test_act_not_mounted_without_on_act(factory):
    c = build(factory)
    seed(factory, "n1")
    assert c.post("/notices/n1/act", json={"action": "done"}).status_code in (404, 405)


def test_act_calls_on_act_after_ownership_and_merges_result(factory):
    calls = []

    def on_act(session, notice, action, user_id, now):
        calls.append((notice.id, action, user_id, now))
        return {"task": {"id": notice.source_id}}

    after = []
    c = build(factory, on_act=on_act, after_act=lambda bg, n, res: after.append(res))
    seed(factory, "n1")
    body = c.post("/notices/n1/act", json={"action": "done"}).json()
    assert calls == [("n1", "done", "u1", NOW)]
    assert body["task"] == {"id": "t1"} and body["notice"]["read_at"] is not None
    assert after == [{"task": {"id": "t1"}}]
    assert c.post("/notices/n1/act", json={"action": "bogus"}).status_code == 422
    assert c.post("/notices/n1/act", json={"action": "done", "x": 1}).status_code == 422


def test_act_by_a_non_owner_is_refused_before_on_act(factory):
    calls = []
    c = build(factory, on_act=lambda *a: calls.append(a))
    seed(factory, "n1", user="u2")
    r = c.post("/notices/n1/act", json={"action": "done"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_notice_owner"
    assert c.post("/notices/missing/act", json={"action": "done"}).status_code == 404
    assert calls == []


def test_on_act_failure_rolls_back_and_keeps_notice_unread(factory):
    def on_act(*a):
        raise HTTPException(409, detail="boom")

    c = build(factory, on_act=on_act)
    seed(factory, "n1")
    assert c.post("/notices/n1/act", json={"action": "done"}).status_code == 409
    assert c.get("/notices").json()["unread_count"] == 1


def test_act_dep_and_custom_actions(factory):
    def need_key(x_key: str | None = Header(None)):
        if x_key != "ok":
            raise HTTPException(403, detail="no")

    c = build(factory, on_act=lambda *a: None, act_dep=need_key, actions=("open",))
    seed(factory, "n1")
    assert c.post("/notices/n1/act", json={"action": "open"}).status_code == 403
    ok = c.post("/notices/n1/act", json={"action": "open"}, headers={"x-key": "ok"})
    assert ok.status_code == 200 and set(ok.json()) == {"notice"}
    assert c.post("/notices/n1/act", json={"action": "done"}, headers={"x-key": "ok"}).status_code == 422
