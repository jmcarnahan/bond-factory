"""GET and PUT /tasks/settings."""

import pytest
from connections_util import headers
from fastapi.testclient import TestClient

DEFAULTS = {"time_zone": None, "start_of_day": "08:00", "end_of_day": "17:00", "lead_minutes": 60, "warnings": [],
            "overridden": []}


@pytest.fixture
def h(client):
    return headers(client)


def code(reply) -> str:
    return reply.json()["detail"]["code"]


def test_defaults_when_nothing_is_stored(client, h):
    assert client.get("/tasks/settings", headers=h).json() == DEFAULTS


def test_put_changes_only_the_fields_sent_and_get_reads_them_back(client, h):
    body = client.put("/tasks/settings", json={"time_zone": "America/Denver", "lead_minutes": 30}, headers=h).json()
    assert body == {**DEFAULTS, "time_zone": "America/Denver", "lead_minutes": 30,
                    "overridden": ["time_zone", "lead_minutes"]}
    client.put("/tasks/settings", json={"end_of_day": "18:30"}, headers=h)
    assert client.get("/tasks/settings", headers=h).json() == {
        **DEFAULTS, "time_zone": "America/Denver", "lead_minutes": 30, "end_of_day": "18:30",
        "overridden": ["time_zone", "end_of_day", "lead_minutes"]}


def test_settings_are_per_person(client, h):
    client.put("/tasks/settings", json={"lead_minutes": 5}, headers=h)
    other = headers(client, "demo-user-2")
    assert client.get("/tasks/settings", headers=other).json()["lead_minutes"] == 60


def test_refusals(client, h):
    assert code(client.put("/tasks/settings", json={"time_zone": "Mars/Base"}, headers=h)) == "invalid_time_zone"
    same = client.put("/tasks/settings", json={"start_of_day": "09:00", "end_of_day": "09:00"}, headers=h)
    assert same.status_code == 422 and code(same) == "invalid_work_day"
    assert client.put("/tasks/settings", json={"start_of_day": "9am"}, headers=h).status_code == 422
    assert client.put("/tasks/settings", json={"lead_minutes": -1}, headers=h).status_code == 422
    assert client.put("/tasks/settings", json={"colour": "red"}, headers=h).status_code == 422


def test_warnings_do_not_block_the_write(client, h):
    body = client.put("/tasks/settings", json={"start_of_day": "09:00", "end_of_day": "10:00",
                                                "lead_minutes": 180}, headers=h).json()
    assert set(body["warnings"]) == {"lead_longer_than_work_day", "time_zone_unknown"}
    assert body["end_of_day"] == "10:00" and body["lead_minutes"] == 180
    stored = client.put("/tasks/settings", json={"time_zone": "UTC", "lead_minutes": 30}, headers=h).json()
    assert stored["warnings"] == []


def test_a_later_end_of_day_moves_the_deadline_of_a_date_only_task(client, h):
    client.put("/tasks/settings", json={"time_zone": "UTC"}, headers=h)
    task = client.post("/tasks", json={"title": "By evening", "due_date": "2026-11-09"}, headers=h).json()
    assert task["due_at"] == "2026-11-09T17:00:00Z"
    client.put("/tasks/settings", json={"end_of_day": "20:00"}, headers=h)
    assert client.get(f"/tasks/{task['id']}", headers=h).json()["due_at"] == "2026-11-09T20:00:00Z"


def test_it_needs_a_session(app):
    assert TestClient(app).get("/tasks/settings").status_code == 401
    assert TestClient(app).put("/tasks/settings", json={}).status_code == 401
