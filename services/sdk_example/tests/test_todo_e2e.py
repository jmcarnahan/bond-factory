"""A phrase becomes tasks, the clock moves, the inbox and the phone get the three stages, done stops it."""

import pytest
from connections_util import headers
from todo_util import expected_id, inbox, notices_of, pushed, register_phone, sweep, timed

PHRASE = "Call Sam tomorrow, send the appraisal to Dana Friday at noon, and I am off tomorrow"
CLOSE, DUE, PAST = "2026-11-13T11:30:00Z", "2026-11-13T12:05:00Z", "2026-11-13T12:40:00Z"


@pytest.fixture
def h(client):
    return headers(client)


def create_from(client, h, candidate) -> dict:
    """What the review screen does: save a candidate through the normal create route."""
    links = [{"kind": "contact", "id": link["candidates"][0]["id"], "label": link["candidates"][0]["label"]}
             for link in candidate["links"] if link["candidates"]]
    reply = client.post("/tasks", json={
        "title": candidate["title"], "due_date": candidate["due_date"], "due_time": candidate["due_time"],
        "priority": candidate["priority"], "links": links, "time_zone": "UTC", "source": "capture"}, headers=h)
    assert reply.status_code == 201, reply.text
    return reply.json()


def test_phrase_to_done(client, app, h):
    register_phone(client, h)
    parsed = client.post("/tasks/parse", json={"text": PHRASE}, headers=h).json()
    assert parsed["degraded"] is False and [i["kind"] for i in parsed["items"]] == ["task", "task", "event"]
    assert client.get("/tasks", headers=h).json()["total"] == 0  # parsing creates nothing
    call, appraisal = [create_from(client, h, c) for c in parsed["items"][:2]]
    assert appraisal["priority"] == 3 and appraisal["due_at"] == "2026-11-13T12:00:00Z"
    assert appraisal["links"][0]["label"].startswith("Dana ")

    for instant in (CLOSE, DUE, PAST):
        assert sweep(client, h, instant)["sweep"]["errors"] == 0

    ids = [expected_id(app, appraisal["id"], stage) for stage in ("close", "due", "past")]
    stored = [n for n in inbox(client, h) if n["data"]["task_id"] == appraisal["id"]]
    assert sorted(n["id"] for n in stored) == sorted(ids)
    assert {n["data"]["stage"] for n in stored} == {"close", "due", "past"}
    assert all(n["data"]["actions"] == ["done", "snooze", "cancel"] for n in stored)
    assert all(n["data"]["route"] == f"/tasks/{appraisal['id']}" for n in stored)

    sent = pushed(client, h, appraisal["id"])
    assert sorted(m["collapse_id"] for m in sent) == sorted(ids)  # the phone collapses on the notice id
    assert {m["token"] for m in sent} == {"tok-demo-1"} and all(m["data"]["notice_id"] == m["collapse_id"] for m in sent)

    before = len(notices_of(app, appraisal["id"]))
    done = client.post(f"/tasks/{appraisal['id']}/complete", headers=h)
    assert done.status_code == 200 and done.json()["status"] == "done"
    assert [n for n in inbox(client, h) if n["data"]["task_id"] == appraisal["id"]] == []  # put away
    assert all(n.dismissed_at is not None for n in notices_of(app, appraisal["id"]))
    for instant in ("2026-11-14T08:30:00Z", "2026-11-15T08:30:00Z"):
        sweep(client, h, instant)
    assert len(notices_of(app, appraisal["id"])) == before  # the series stopped
    assert len(pushed(client, h, appraisal["id"])) == 3
    assert call["id"] != appraisal["id"]


def test_a_second_sweep_at_the_same_instant_changes_nothing(client, app, h):
    register_phone(client, h)
    task = timed(client, h)
    first = sweep(client, h, "2026-11-09T10:05:00Z")
    again = sweep(client, h, "2026-11-09T10:05:00Z")
    assert first["sweep"]["claimed"] == 1 and again["sweep"]["claimed"] == 0
    assert len(notices_of(app, task["id"])) == 1 and len(pushed(client, h, task["id"])) == 1
