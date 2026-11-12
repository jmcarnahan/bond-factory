"""A disabled /fake/clock answers exactly what an unmounted path answers."""

import pytest
from fastapi import Depends, FastAPI, Header
from fastapi.testclient import TestClient

from bond_service_kit import Clock, fake_clock_router, install_error_handlers


def need_key(x_key: str = Header(...)) -> None:
    pass


def build(enabled, handlers=True):
    clock = Clock()
    app = FastAPI()
    if handlers:
        install_error_handlers(app)
    app.include_router(fake_clock_router(clock, enabled=enabled, dependencies=[Depends(need_key)]))
    return clock, TestClient(app, raise_server_exceptions=False)


def _same(c, send, path="/fake/clock"):
    ref = send("/nope")
    got = send(path)
    assert got.status_code == ref.status_code == 404
    assert got.content == ref.content and got.headers.get("content-type") == ref.headers.get("content-type")


@pytest.mark.parametrize("handlers", [True, False])
@pytest.mark.parametrize("path", ["/fake/clock", "/fake/clock/"])
def test_disabled_matches_unmounted_for_every_verb_and_body(handlers, path):
    clock, c = build(lambda: False, handlers)
    bad = {"content-type": "application/json"}
    _same(c, lambda p: c.put(p, content=b"{not json", headers=bad), path)
    _same(c, lambda p: c.put(p, json={"now": 5}), path)
    _same(c, lambda p: c.put(p, json={"now": "2026-11-08T10:30:00Z"}, headers={"x-key": "k"}), path)
    _same(c, lambda p: c.post(p, json={}), path)
    _same(c, lambda p: c.delete(p), path)
    _same(c, lambda p: c.patch(p, json={}), path)
    _same(c, lambda p: c.get(p), path)
    _same(c, lambda p: c.get(p, headers={"x-key": "k"}), path)
    _same(c, lambda p: c.options(p), path)
    assert not clock.frozen
    head, ref = c.head(path, follow_redirects=False), c.head("/nope")
    assert head.status_code == ref.status_code == 404


def test_enabled_behaviour_is_unchanged():
    _clock, c = build(lambda: True)
    h = {"x-key": "k"}
    assert c.get("/fake/clock", headers=h).json() == {"now": None}
    assert c.get("/fake/clock").status_code == 422  # auth dependency still applies
    assert c.put("/fake/clock", json={"now": "2026-11-08T10:30:00Z"}, headers=h).status_code == 200
    r = c.post("/fake/clock", json={}, headers=h)
    assert r.status_code == 405 and r.headers["allow"] == "GET, PUT"
    r = c.get("/fake/clock/", headers=h, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith("/fake/clock")


def test_empty_string_is_422_not_a_release():
    clock, c = build(lambda: True)
    h = {"x-key": "k"}
    c.put("/fake/clock", json={"now": "2026-11-08T10:30:00Z"}, headers=h)
    r = c.put("/fake/clock", json={"now": ""}, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_now"
    assert clock.frozen
    assert c.put("/fake/clock", json={"now": None}, headers=h).json() == {"now": None}


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+05:00", "9999-12-31T23:59:59-05:00"])
def test_out_of_range_instant_is_422(value):
    clock, c = build(lambda: True)
    r = c.put("/fake/clock", json={"now": value}, headers={"x-key": "k"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_now"
    assert not clock.frozen
