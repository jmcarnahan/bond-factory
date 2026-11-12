"""PUT /fake/clock: a pin that lasts, so the server and a demo's fake clock agree between ticks."""

import pytest
from connections_util import headers
from todo_util import sweep, timed

CHICAGO = "America/Chicago"  # the 17:00 task below is due 23:00 UTC


@pytest.fixture
def h(client):
    return headers(client)


def pin(client, h, now):
    reply = client.put("/fake/clock", json={"now": now}, headers=h)
    assert reply.status_code == 200
    return reply.json()


def today(client, h):
    return client.get("/tasks/today", params={"time_zone": CHICAGO}, headers=h).json()


def test_the_pin_decides_today_and_overdue_and_the_summary_agrees(client, h):
    timed(client, h, title="Five", at="17:00", zone=CHICAGO)
    assert pin(client, h, "2026-11-09T22:59:00Z") == {"now": "2026-11-09T22:59:00Z"}
    assert [t["title"] for t in today(client, h)["today"]] == ["Five"]
    assert client.get("/fake/clock", headers=h).json() == {"now": "2026-11-09T22:59:00Z"}
    pin(client, h, "2026-11-09T23:01:00Z")
    body = today(client, h)
    assert [t["title"] for t in body["overdue"]] == ["Five"] and body["today"] == []
    summary = client.get("/tasks/summary", params={"time_zone": CHICAGO}, headers=h).json()
    assert summary["overdue"] == 1 and summary["due_today"] == 0


def test_a_tick_with_now_keeps_the_earlier_pin_and_one_without_uses_it(client, app, h):
    task = timed(client, h)
    pin(client, h, "2026-11-09T10:05:00Z")
    body = sweep(client, h, "2026-11-09T09:30:00Z")
    assert body["sweep"]["claimed"] == 1
    assert client.get("/fake/clock", headers=h).json() == {"now": "2026-11-09T10:05:00Z"}
    assert app.state.clock.frozen and app.state.clock.utcnow_naive().isoformat() == "2026-11-09T10:05:00"
    bare = client.post("/jobs/tick", json={}, headers=h).json()  # no now: the pinned 10:05, the due stage
    assert bare["sweep"]["claimed"] == 1
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["overdue"] is True


def test_unpinning_returns_to_real_time(client, app, h):
    pin(client, h, "2026-11-09T10:05:00Z")
    assert pin(client, h, None) == {"now": None}
    assert app.state.clock.frozen is False
    sweep(client, h, "2026-11-09T10:00:00Z")
    assert app.state.clock.frozen is False  # nothing pinned: a tick still releases the clock


def test_a_bad_instant_is_422_and_real_mode_is_404(client, app, h):
    assert client.put("/fake/clock", json={"now": "soon"}, headers=h).status_code == 422
    object.__setattr__(app.state.settings, "mode", "real")
    assert client.put("/fake/clock", json={"now": None}, headers=h).status_code == 404
    assert client.get("/fake/clock", headers=h).status_code == 404
