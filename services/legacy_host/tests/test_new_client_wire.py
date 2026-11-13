"""Trait 5 (Python half): a NEW client, the SDK's Dart `TaskDraft` / `TaskPatch`, talks to the legacy host.

The request files are what the Dart `toJson()` emits (the Dart test of the SDK reads the same files); the answer files
are recorded from this host. `BOND_REGEN_FIXTURES=1` rewrites the answers, otherwise they are compared as parsed JSON.
Recorded instants end in `.000000` so a Dart round trip (millisecond precision) loses nothing.
"""

import json
import os
from pathlib import Path

import pytest
from conftest import as_user
from sqlalchemy import text

from legacy_host.models import Task

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "legacy_host"
OWNER, EDITOR = as_user("u-owner"), as_user("u-editor")


def read(name):
    return json.loads((FIXTURES / name).read_text())


def check(name, actual):
    path = FIXTURES / name
    if os.environ.get("BOND_REGEN_FIXTURES") == "1":
        path.write_text(json.dumps(actual, indent=2) + "\n")
    assert actual == json.loads(path.read_text()), f"{name} differs; BOND_REGEN_FIXTURES=1 rewrites it"


@pytest.fixture
def drafted(client):
    r = client.post("/tasks", json=read("draft_request.json"), headers=OWNER)
    assert r.status_code == 201, r.text
    return client, r.json()


def test_draft_is_accepted_and_stored(drafted, session):
    _, item = drafted
    row = session.get(Task, "task-draft-1")
    assert (row.title, row.notes, row.priority, row.assigned_user_id) == (
        "Send the signed form", "Use the blue folder", 3, "u-editor")
    assert (row.client_ref, row.case_ref, row.remind_minutes_before, row.source) == ("cl-1", "ca-1", 30, "manual")
    assert [c["text"] for c in row.checklist] == ["Print", "Sign"] and row.checklist[1]["done_at"]
    assert row.links[0]["id"] == "c-1" and row.mirror_enabled is True
    assert row.due_at.isoformat() == "2026-11-09T17:30:00"  # 09:30 in Los Angeles; the hint agrees
    assert item["id"] == "task-draft-1"


def test_task_item_answer_is_recorded(drafted):
    check("task_item.json", drafted[1])


def test_task_list_answer_is_recorded(drafted):
    client, _ = drafted
    client.post("/tasks", json={"id": "task-plain-1", "title": "Plain", "remind_minutes_before": -3,
                                "mirror_enabled": True, "checklist": [], "links": []}, headers=OWNER)
    check("task_list.json", client.get("/tasks?status=all", headers=OWNER).json())


def test_error_not_owner_answer_is_recorded(drafted):
    client, _ = drafted
    r = client.put("/tasks/task-draft-1", json={"client_ref": "cl-2"}, headers=EDITOR)
    assert r.status_code == 403
    check("error_not_owner.json", r.json())


def test_patch_is_accepted_and_clears(drafted, session):
    client, _ = drafted
    r = client.put("/tasks/task-draft-1", json=read("patch_request.json"), headers=OWNER)
    assert r.status_code == 200, r.text
    row = session.get(Task, "task-draft-1")
    assert (row.title, row.notes, row.due_time, row.assigned_user_id, row.priority) == (
        "Send the form", None, None, None, None)
    assert (str(row.due_date), row.links, row.mirror_enabled) == ("2026-11-09", [], False)
    assert (row.case_ref, row.client_ref) == ("ca-2", "cl-2")  # the case brought its client
    assert row.due_at is not None  # a date-only task keeps a computed instant
    assert r.json()["sync_to_calendar"] is False


def test_echoed_response_keys_never_override_or_write(drafted, session):
    """The SDK client echoes what it read: bond's `mirror_enabled` wins over a stale `sync_to_calendar`, and the
    response-only keys are not written."""
    client, _ = drafted
    r = client.put("/tasks/task-draft-1", json={"mirror_enabled": False, "sync_to_calendar": True,
                                                "calendar_event_id": "stale", "client_name": "x",
                                                "case_label": "y"}, headers=OWNER)
    assert r.status_code == 200, r.text
    raw = session.execute(text("SELECT sync_to_calendar, calendar_event_id FROM tasks WHERE id = 'task-draft-1'")).one()
    assert tuple(raw) == (0, None)
    assert (r.json()["client_name"], r.json()["case_label"]) == ("Acme Test Co", "Case One")
