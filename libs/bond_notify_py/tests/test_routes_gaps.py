"""``make_notices_router``: result-key precedence, coded errors from ``on_act``, ``error_map``, read-all count."""

import pytest
from conftest import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_routes import build, seed

from bond_notify_py.errors import NoticeError


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class Coded(Exception):
    """Shaped like a coded error from another lib; this file imports none."""

    def __init__(self, code, message, status):
        super().__init__(code)
        self.code, self.message, self.status = code, message, status


def test_notice_key_always_wins_over_an_on_act_result_key(factory):
    c = build(factory, on_act=lambda *a: {"notice": "hijack", "extra": 1})
    seed(factory, "n1")
    body = c.post("/notices/n1/act", json={"action": "done"}).json()
    assert body["notice"]["id"] == "n1" and body["extra"] == 1
    assert next(iter(body)) == "notice"


def test_coded_error_from_on_act_is_answered_by_default(factory):
    def on_act(*a):
        raise Coded("not_task_owner", "Only the owner may do that.", 403)

    c = build(factory, on_act=on_act)
    seed(factory, "n1")
    r = c.post("/notices/n1/act", json={"action": "done"})
    assert r.status_code == 403
    assert r.json() == {"detail": {"code": "not_task_owner", "message": "Only the owner may do that."}}
    assert c.get("/notices").json()["unread_count"] == 1  # rolled back: still unread


@pytest.mark.parametrize("exc", [Coded(1, "m", 403), Coded("c", None, 403), Coded("c", "m", "403"),
                                 Coded("c", "m", True), ValueError("plain")])
def test_other_exceptions_are_not_swallowed(factory, exc):
    def on_act(*a):
        raise exc

    c = build(factory, on_act=on_act)
    seed(factory, "n1")
    with pytest.raises(type(exc)):
        c.post("/notices/n1/act", json={"action": "done"})


def test_an_exception_with_its_own_detail_is_left_to_the_app(factory):
    class Own(Coded):
        def detail(self):
            return {"code": self.code, "message": self.message, "hint": "h"}

    def on_act(*a):
        raise Own("c", "m", 403)

    c = build(factory, on_act=on_act)
    seed(factory, "n1")
    with pytest.raises(Own):
        c.post("/notices/n1/act", json={"action": "done"})


def test_notice_error_still_answers(factory):
    c = build(factory)
    r = c.post("/notices/missing/read")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "notice_not_found"
    assert isinstance(NoticeError("x"), Exception)


def test_error_map_answers_any_escaping_exception(factory):
    seen = []

    def error_map(exc):
        seen.append(type(exc).__name__)
        if isinstance(exc, Coded):
            return 409, {"error": exc.code}
        return None  # NoticeError and others: not answered, so they propagate

    def on_act(*a):
        raise Coded("clash", "m", 403)

    c = build(factory, on_act=on_act, error_map=error_map)
    seed(factory, "n1")
    r = c.post("/notices/n1/act", json={"action": "done"})
    assert r.status_code == 409 and r.json() == {"error": "clash"}
    with pytest.raises(NoticeError):  # a custom map replaces the default rule
        c.post("/notices/missing/read")
    assert seen == ["Coded", "NoticeError"]


def test_error_map_can_answer_a_notice_error(factory):
    c = build(factory, error_map=lambda exc: (418, {"e": getattr(exc, "code", "?")}))
    r = c.post("/notices/missing/read")
    assert r.status_code == 418 and r.json() == {"e": "notice_not_found"}


def test_read_all_returns_the_real_unread_count(factory):
    c = build(factory)
    seed(factory, "a1", user="u1")
    seed(factory, "a2", user="u1")
    seed(factory, "b1", user="u2")
    seed(factory, "b2", user="u2")
    seed(factory, "b3", user="u2")
    assert c.get("/notices", headers={"x-user": "u2"}).json()["unread_count"] == 3
    assert c.post("/notices/read-all", headers={"x-user": "u1"}).json() == {"unread_count": 0}
    assert c.get("/notices", headers={"x-user": "u2"}).json()["unread_count"] == 3  # not touched
    # a notice that stays unread after read-all would show: dismissed ones do not count, new ones do
    seed(factory, "a3", user="u1")
    assert c.get("/notices", headers={"x-user": "u1"}).json()["unread_count"] == 1


@pytest.mark.parametrize("bad", [lambda exc: "nope", lambda exc: ("418", {}), lambda exc: (True, {}), lambda exc: 1 / 0])
def test_a_bad_error_map_is_a_type_error_that_names_it_and_keeps_the_cause(factory, bad):
    c = build(factory, error_map=bad)
    with pytest.raises(TypeError, match="error_map") as caught:
        c.post("/notices/missing/read")
    assert isinstance(caught.value.__cause__, NoticeError)  # the original error is not hidden
