"""POST /tasks/parse, the link search and the accepted-event stub."""

import pytest
from connections_util import headers
from fastapi.testclient import TestClient

from sdk_example.models.task_links import TaskLinkIndex

TEXT = "Call Sam tomorrow, send the appraisal to Dana Friday at noon, and I am off tomorrow"


@pytest.fixture
def h(client):
    return headers(client)


def code(reply) -> str:
    return reply.json()["detail"]["code"]


def parse(client, h, text=TEXT, **extra):
    return client.post("/tasks/parse", json={"text": text, **extra}, headers=h)


def test_a_phrase_gives_two_tasks_and_an_event_and_creates_nothing(client, h):
    body = parse(client, h, today="2026-11-11", time_zone="America/Denver").json()
    assert body["degraded"] is False and body["reason"] is None
    assert [i["kind"] for i in body["items"]] == ["task", "task", "event"]
    sam = body["items"][0]["links"][0]
    assert sam["text"] == "Sam" and [c["label"] for c in sam["candidates"]] == ["Sam Rivera", "Samira Ortiz"]
    assert body["items"][2]["all_day"] is True
    assert client.get("/tasks", params={"status": "all"}, headers=h).json()["total"] == 0


def test_no_model_gives_one_degraded_draft_and_not_an_error(client, h):
    assert client.put("/fake/capture", json={"down": True}, headers=h).json() == {"down": True}
    body = parse(client, h, "Pay the invoice tomorrow at 3pm").json()
    assert body["degraded"] is True and body["reason"] == "model_unavailable"
    [draft] = body["items"]
    assert draft["kind"] == "task" and draft["degraded"] is True and draft["due_time"] == "15:00"
    client.put("/fake/capture", json={"down": False}, headers=h)
    assert parse(client, h).json()["degraded"] is False


def test_real_mode_without_a_vendor_client_degrades(client, app, h):
    app.state.capture_llm = None
    assert parse(client, h).json()["reason"] == "model_unavailable"


def test_the_guard_answers_429_and_is_per_person(client, h):
    client.put("/fake/capture/limit", json={"limit": 2}, headers=h)
    assert parse(client, h).status_code == 200 and parse(client, h).status_code == 200
    third = parse(client, h)
    assert third.status_code == 429 and code(third) == "capture_denied"
    other = headers(client, "demo-user-2")
    assert parse(client, other).status_code == 200


def test_the_text_limits(client, h):
    for text in ("", "   "):
        reply = parse(client, h, text)
        assert reply.status_code == 422 and code(reply) == "text_required"
    assert parse(client, h, "x" * 500).status_code == 200
    long = parse(client, h, "x" * 501)
    assert long.status_code == 422 and code(long) == "text_too_long"
    assert client.post("/tasks/parse", json={"text": "a", "extra": 1}, headers=h).status_code == 422


def test_a_bad_zone_is_422(client, h):
    reply = parse(client, h, time_zone="Mars/Base")
    assert reply.status_code == 422 and code(reply) == "invalid_time_zone"


def test_link_search_finds_contacts_and_nothing_for_an_empty_query(client, h):
    found = client.get("/tasks/links/search", params={"kind": "contact", "q": "dana"}, headers=h).json()["items"]
    assert [(i["kind"], i["label"]) for i in found] == [("contact", "Dana Park"), ("contact", "Dana Whitfield")]
    assert found[0]["id"] == "c-dana-park"
    assert client.get("/tasks/links/search", params={"q": ""}, headers=h).json() == {"items": []}
    assert client.get("/tasks/links/search", params={"kind": "deal", "q": "dana"}, headers=h).json() == {"items": []}


def test_a_linked_task_is_found_by_contact_and_leaves_no_index_row_after_delete(client, app, h):
    link = {"kind": "contact", "id": "c-lee-harper", "label": "Lee Harper"}
    task = client.post("/tasks", json={"title": "Ring Lee", "links": [link]}, headers=h).json()
    found = client.get("/tasks", params={"link_kind": "contact", "link_id": "c-lee-harper"}, headers=h).json()
    assert [t["id"] for t in found["items"]] == [task["id"]]
    assert client.delete(f"/tasks/{task['id']}", headers=h).status_code == 204
    with app.state.session_factory() as session:
        assert session.query(TaskLinkIndex).count() == 0


def test_an_accepted_event_is_recorded_for_the_demo(client, h):
    event = {"title": "Day off", "start_date": "2026-11-12", "all_day": True}
    saved = client.post("/capture/events", json=event, headers=h)
    assert saved.status_code == 201 and saved.json()["title"] == "Day off"
    assert [e["title"] for e in client.get("/capture/events", headers=h).json()["items"]] == ["Day off"]
    assert client.get("/capture/events", headers=headers(client, "demo-user-2")).json() == {"items": []}


def test_the_fake_switches_are_fake_mode_only_and_parse_needs_a_session(client, app, h):
    assert TestClient(app).post("/tasks/parse", json={"text": "a"}).status_code == 401
    object.__setattr__(app.state.settings, "mode", "real")
    assert client.put("/fake/capture", json={"down": True}, headers=h).status_code == 404
    assert client.get("/fake/push/sent", headers=h).status_code == 404


def test_rich_is_opt_in_and_the_default_answer_has_no_rich_keys(client, h):
    plain = parse(client, h, today="2026-11-11").json()
    assert plain == parse(client, h, today="2026-11-11", rich=False).json()
    assert not {"location", "notes", "duration_minutes", "attendees"} & set(plain["items"][2])


def test_rich_gives_location_notes_duration_and_attendees(client, h):
    body = parse(client, h, "Site meeting at 2pm, call Sam", today="2026-11-11", rich=True).json()
    event, task = body["items"]
    assert event["kind"] == "event" and event["location"] == "Example Plaza office"
    assert event["notes"] == "Bring the permit drawings" and event["duration_minutes"] == 90
    assert event["attendees"] == ["Dana", "Lee"] and event["end_time"] == "15:30"
    assert task["notes"] == "Ask about the invoice"
