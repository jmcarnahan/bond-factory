"""The fake clock router, the sync upload's `server_now`, and the 503 the kit middleware answers (adoption-gap seams)."""

import pytest
from connections_util import headers
from fastapi.testclient import TestClient

PIN = "2026-11-09T10:05:00Z"
EMPTY_UPLOAD = {"transaction_id": 1, "ops": []}


@pytest.fixture
def h(client):
    return headers(client)


def test_the_clock_routes_come_from_the_kit_router_and_need_a_session(app):
    from sdk_example.routes import fake_todo

    assert fake_todo.fake_clock_router.__module__.startswith("bond_service_kit")
    assert TestClient(app).get("/fake/clock").status_code == 401
    assert TestClient(app).put("/fake/clock", json={"now": PIN}).status_code == 401


def test_an_offset_is_converted_and_an_empty_body_or_null_releases_the_pin(client, app, h):
    reply = client.put("/fake/clock", json={"now": "2026-11-09T12:05:00+02:00"}, headers=h)
    assert reply.json() == {"now": PIN}
    assert app.state.clock_pin is not None and app.state.clock.frozen
    assert client.put("/fake/clock", json={}, headers=h).json() == {"now": None}
    assert app.state.clock_pin is None and app.state.clock.frozen is False
    bad = client.put("/fake/clock", json={"now": "soon"}, headers=h)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_now"


def test_a_clock_frozen_by_something_else_is_not_a_pin(client, app, h):
    assert app.state.clock.frozen  # the fixture froze it; PUT /fake/clock did not
    assert client.get("/fake/clock", headers=h).json() == {"now": None}


def test_real_mode_answers_404_before_it_reads_the_body(client, app, h):
    object.__setattr__(app.state.settings, "mode", "real")
    assert client.put("/fake/clock", json={"now": 5}, headers=h).status_code == 404  # not a 422


def test_the_upload_reports_the_pinned_time(client, h):
    client.put("/fake/clock", json={"now": PIN}, headers=h)
    reply = client.post("/sync/upload", json=EMPTY_UPLOAD, headers=h)
    assert reply.status_code == 200
    assert reply.json()["server_now"] == "2026-11-09T10:05:00.000Z"
    client.put("/fake/clock", json={"now": "2026-11-09T11:30:15Z"}, headers=h)
    assert client.post("/sync/upload", json=EMPTY_UPLOAD, headers=h).json()["server_now"] == "2026-11-09T11:30:15.000Z"


def test_the_upload_follows_the_app_clock_when_it_is_frozen_elsewhere(client, h):
    assert client.post("/sync/upload", json=EMPTY_UPLOAD, headers=h).json()["server_now"] == "2026-11-08T10:00:00.000Z"


def test_the_sync_token_reports_the_same_pinned_time(client, h, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_SYNC_URL", "http://localhost:8012/powersync-fake")
    client.put("/fake/clock", json={"now": PIN}, headers=h)
    reply = client.post("/sync/token", headers=h)
    assert reply.status_code == 200 and reply.json()["server_now"] == "2026-11-09T10:05:00.000Z"


def test_a_database_outage_is_answered_by_the_middleware_not_the_route(client, h, monkeypatch):
    """The route has no try/except any more: DbUnavailable carries `db_unavailable`, the kit middleware answers 503."""
    from bond_sync_py import DbUnavailable

    from sdk_example.routes import sync as sync_routes

    def down(*args, **kwargs):
        raise DbUnavailable("down")

    monkeypatch.setattr(sync_routes, "upload", down)
    reply = client.post("/sync/upload", json=EMPTY_UPLOAD, headers=h)
    assert reply.status_code == 503 and reply.headers["retry-after"] == "5"
    assert reply.json() == {"detail": {"code": "db_unavailable",
                                       "message": "The database is not answering. Try again in a few seconds"}}
