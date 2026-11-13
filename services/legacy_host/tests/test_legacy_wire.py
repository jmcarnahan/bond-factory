"""Trait 3: the legacy wire. Bond's keys stay, the app's keys are added, instants are naive ISO with microseconds,
errors carry `error_code` beside `code`, and a request body may use either vocabulary."""

import re

import pytest
from bond_tasks_py import ITEM_KEYS
from conftest import as_user

OWNER = as_user("u-owner")
LEGACY_KEYS = ("sync_to_calendar", "calendar_event_id", "client_ref", "case_ref", "client_name", "case_label")
NAIVE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}$")


@pytest.fixture
def item(client):
    body = {"id": "t-1", "title": "Wire", "due_date": "2026-11-09", "due_time": "09:30", "time_zone": "UTC",
            "case_ref": "ca-1", "checklist": [{"text": "step"}]}
    assert client.post("/tasks", json=body, headers=OWNER).status_code == 201
    return client.post("/tasks/t-1/complete", headers=OWNER).json()


def test_item_has_every_bond_key_and_every_legacy_key(item):
    assert set(ITEM_KEYS) <= set(item)
    assert set(LEGACY_KEYS) <= set(item)
    assert set(item) == set(ITEM_KEYS) | set(LEGACY_KEYS)


def test_legacy_keys_carry_the_app_values(item):
    assert item["sync_to_calendar"] is True and item["mirror_enabled"] is True
    assert (item["client_ref"], item["client_name"]) == ("cl-1", "Acme Test Co")
    assert (item["case_ref"], item["case_label"]) == ("ca-1", "Case One")
    assert item["calendar_event_id"] is None and item["owner_name"] == "Olive Owner"


@pytest.mark.parametrize("key", ["completed_at", "created_at", "updated_at", "due_at"])
def test_instants_are_naive_iso_with_microseconds(item, key):
    assert NAIVE.match(item[key]), item[key]
    assert not item[key].endswith("Z")


def test_instant_values(item):
    assert item["created_at"] == "2026-11-08T10:00:00.000000"
    assert item["due_at"] == "2026-11-09T09:30:00.000000"


def test_unset_instants_stay_null(client):
    r = client.post("/tasks", json={"title": "Plain"}, headers=OWNER).json()
    assert (r["completed_at"], r["due_at"]) == (None, None)


def test_the_list_answer_is_items_and_total(client):
    for n in range(3):
        client.post("/tasks", json={"title": f"T{n}"}, headers=OWNER)
    body = client.get("/tasks?limit=2", headers=OWNER).json()
    assert set(body) == {"items", "total"} and body["total"] == 3 and len(body["items"]) == 2
    assert NAIVE.match(body["items"][0]["created_at"])


def error_of(response):
    detail = response.json()["detail"]
    assert set(detail) == {"error_code", "code", "message"}
    assert detail["error_code"] == detail["code"].upper() and detail["message"]
    return detail["code"]


def test_error_not_owner(client):
    client.post("/tasks", json={"id": "t-1", "title": "A", "assigned_user_id": "u-editor"}, headers=OWNER)
    r = client.put("/tasks/t-1", json={"assigned_user_id": "u-admin"}, headers=as_user("u-editor"))
    assert r.status_code == 403 and error_of(r) == "not_task_owner"


def test_error_not_found(client):
    r = client.get("/tasks/missing", headers=OWNER)
    assert r.status_code == 404 and error_of(r) == "task_not_found"


def test_error_title_required(client):
    r = client.post("/tasks", json={"title": "   "}, headers=OWNER)
    assert r.status_code == 422 and error_of(r) == "title_required"
    assert client.post("/tasks", json={}, headers=OWNER).status_code == 422


def test_error_due_time_without_date(client):
    r = client.post("/tasks", json={"title": "A", "due_time": "10:00"}, headers=OWNER)
    assert r.status_code == 422 and error_of(r) == "due_time_requires_date"


def test_error_unauthenticated_and_invalid_body(client):
    r = client.get("/tasks")
    assert r.status_code == 401 and error_of(r) == "unauthorized"
    r = client.post("/tasks", json={"title": "A", "priority": 9}, headers=OWNER)
    assert r.status_code == 422 and error_of(r) == "invalid_request"


def test_error_id_taken(client):
    client.post("/tasks", json={"id": "t-1", "title": "A"}, headers=OWNER)
    r = client.post("/tasks", json={"id": "t-1", "title": "B"}, headers=as_user("u-editor"))
    assert r.status_code == 409 and error_of(r) == "id_taken"


def test_unknown_request_keys_are_ignored(client):
    r = client.post("/tasks", json={"title": "A", "zzz": 1, "legacy_flag": True, "owner_user_id": "u-editor",
                                    "status": "done"}, headers=OWNER)
    assert r.status_code == 201
    assert (r.json()["owner_user_id"], r.json()["status"]) == ("u-owner", "open")  # computed fields are not writable
    r = client.put(f"/tasks/{r.json()['id']}", json={"zzz": [1], "title": "B"}, headers=OWNER)
    assert r.status_code == 200 and r.json()["title"] == "B"


def test_a_body_with_only_legacy_keys(client):
    r = client.post("/tasks", json={"title": "Legacy", "sync_to_calendar": 0, "client_ref": "cl-2"}, headers=OWNER)
    assert r.status_code == 201
    assert (r.json()["mirror_enabled"], r.json()["sync_to_calendar"], r.json()["client_ref"]) == (False, False, "cl-2")
    r = client.put(f"/tasks/{r.json()['id']}", json={"sync_to_calendar": True}, headers=OWNER)
    assert r.json()["mirror_enabled"] is True


def test_a_body_with_only_bond_keys(client):
    body = {"title": "Bond", "mirror_enabled": False, "priority": 2, "remind_minutes_before": 15,
            "links": [{"kind": "contact", "id": "c-1", "label": "Pat"}], "checklist": [{"text": "one", "done": True}],
            "source": "capture"}
    r = client.post("/tasks", json=body, headers=OWNER)
    assert r.status_code == 201, r.text
    item = r.json()
    assert (item["sync_to_calendar"], item["priority"], item["remind_minutes_before"], item["source"]) == (
        False, 2, 15, "capture")
    assert item["links"][0]["id"] == "c-1" and item["checklist"][0]["done_at"] is not None


def test_bond_key_wins_when_both_spellings_are_sent(client):
    r = client.post("/tasks", json={"title": "Both", "mirror_enabled": True, "sync_to_calendar": False}, headers=OWNER)
    assert r.json()["mirror_enabled"] is True


def test_null_in_a_field_bond_refuses_null_means_not_sent(client):
    r = client.post("/tasks", json={"title": "A", "checklist": None, "links": None, "mirror_enabled": None,
                                    "remind_minutes_before": None}, headers=OWNER)
    assert r.status_code == 201 and r.json()["checklist"] == [] and r.json()["mirror_enabled"] is True


def test_delete_answers_204_then_404(client):
    client.post("/tasks", json={"id": "t-1", "title": "A"}, headers=OWNER)
    assert client.delete("/tasks/t-1", headers=OWNER).status_code == 204
    assert error_of(client.get("/tasks/t-1", headers=OWNER)) == "task_not_found"
