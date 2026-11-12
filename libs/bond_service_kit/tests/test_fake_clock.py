from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from bond_service_kit import Clock, fake_clock_router, install_error_handlers


def make(enabled=lambda: True, **kw):
    clock = Clock()
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(fake_clock_router(clock, enabled=enabled, **kw))
    return clock, TestClient(app)


def test_pin_and_read_back_then_null_releases():
    clock, c = make()
    assert c.get("/fake/clock").json() == {"now": None}
    r = c.put("/fake/clock", json={"now": "2026-11-08T10:30:00Z"})
    assert r.status_code == 200 and r.json() == {"now": "2026-11-08T10:30:00Z"}
    assert c.get("/fake/clock").json() == {"now": "2026-11-08T10:30:00Z"}
    assert clock.now() == datetime(2026, 11, 8, 10, 30, tzinfo=UTC)
    assert c.put("/fake/clock", json={"now": None}).json() == {"now": None}
    assert not clock.frozen
    c.put("/fake/clock", json={"now": "2026-11-08T10:30:00Z"})
    assert c.put("/fake/clock", json={}).json() == {"now": None}


def test_offsets_convert_and_naive_is_utc():
    _, c = make()
    assert c.put("/fake/clock", json={"now": "2026-11-08T10:30:00-08:00"}).json() == {"now": "2026-11-08T18:30:00Z"}
    assert c.put("/fake/clock", json={"now": "2026-11-08T10:30:00"}).json() == {"now": "2026-11-08T10:30:00Z"}


def test_bad_iso_is_422_and_does_not_change_the_pin():
    clock, c = make()
    r = c.put("/fake/clock", json={"now": "tomorrow"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_now"
    assert not clock.frozen


def test_disabled_answers_404_even_with_a_valid_or_invalid_body():
    clock, c = make(enabled=lambda: False)
    assert c.get("/fake/clock").status_code == 404
    r = c.put("/fake/clock", json={"now": "2026-11-08T10:30:00Z"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    assert c.put("/fake/clock", json={"bogus": 1}).status_code == 404
    assert c.put("/fake/clock", content=b"not json").status_code == 404
    assert not clock.frozen


def test_enabled_is_checked_per_request():
    state = {"on": False}
    _, c = make(enabled=lambda: state["on"])
    assert c.get("/fake/clock").status_code == 404
    state["on"] = True
    assert c.get("/fake/clock").status_code == 200
    state["on"] = False
    assert c.get("/fake/clock").status_code == 404


def test_extra_dependencies_run_after_the_gate():
    def deny():
        raise HTTPException(401, "unauthorized")

    _, c = make(dependencies=[Depends(deny)])
    assert c.get("/fake/clock").status_code == 401
    _, c = make(enabled=lambda: False, dependencies=[Depends(deny)])
    assert c.get("/fake/clock").status_code == 404
