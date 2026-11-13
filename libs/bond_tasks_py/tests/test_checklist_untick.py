"""An unticked item as a client sends it: `done: false` unticks; an omitted `done` keeps the stored tick (old clients)."""

import json
from dataclasses import dataclass
from datetime import timedelta

import pytest
from conftest import NOW, Task
from test_service import USERS, edit, make

from bond_tasks_py import TaskUpdate, service, sync_routes

ROUTE = sync_routes(Task, now=lambda: NOW)[("tasks", None)]
STAMP = "2026-11-08T12:00:00Z"
OLD = {"id": "c1", "text": "A", "done_at": None}  # what ChecklistItem.toJson emitted before `done` was added
NEW_OPEN = {"id": "c1", "text": "A", "done": False, "done_at": None}
NEW_DONE = {"id": "c1", "text": "A", "done": True, "done_at": STAMP}


@dataclass
class Op:
    id: str
    op: str


@dataclass
class Ctx:
    user: object
    background: object = None


def call(session, op, data):
    return ROUTE.handler(session, Ctx("u1"), Op("t1", op), data)


def ticked_task(session):
    call(session, "put", {"title": "A", "checklist": [{"id": "c1", "text": "A", "done": True}]})
    assert session.get(Task, "t1").checklist[0]["done_at"] == STAMP


def done_at(session):
    return session.get(Task, "t1").checklist[0]["done_at"]


@pytest.mark.parametrize("wrap", [lambda items: items, json.dumps], ids=["list", "json-text"])
def test_sync_patch_old_body_keeps_the_tick(session, wrap):
    ticked_task(session)
    call(session, "patch", {"checklist": wrap([OLD])})
    assert done_at(session) == STAMP, "an omitted `done` keeps the stored tick"


@pytest.mark.parametrize("wrap", [lambda items: items, json.dumps], ids=["list", "json-text"])
def test_sync_patch_done_false_unticks(session, wrap):
    ticked_task(session)
    call(session, "patch", {"checklist": wrap([NEW_OPEN])})
    assert done_at(session) is None


@pytest.mark.parametrize("wrap", [lambda items: items, json.dumps], ids=["list", "json-text"])
def test_sync_patch_done_true_keeps_the_first_stamp(session, wrap):
    ticked_task(session)
    call(session, "patch", {"checklist": wrap([{**NEW_DONE, "done_at": "2030-01-01T00:00:00Z"}])})
    assert done_at(session) == STAMP


def test_service_update_old_body_keeps_unticks_with_done_false_and_keeps_first_stamp(session):
    task = make(session, checklist=[{"id": "c1", "text": "A", "done": True}])
    edit(session, task, "u1", checklist=[OLD])
    assert task.checklist[0]["done_at"] == STAMP
    later = NOW + timedelta(hours=3)
    service.update(session, task=task, actor_user_id="u1", data=TaskUpdate.model_validate({"checklist": [NEW_DONE]}),
                   now=later, user_exists=USERS.__contains__)
    assert task.checklist[0]["done_at"] == STAMP
    edit(session, task, "u1", checklist=[NEW_OPEN])
    assert task.checklist[0]["done_at"] is None


def test_stale_copy_resend_with_a_new_item_keeps_another_persons_tick(session):
    """The exact body a phone sends after adding an item to a list it never saw ticked (`ChecklistItem.toJson`
    of a never-ticked item has no `done`)."""
    ticked_task(session)
    call(session, "patch", {"checklist": [OLD, {"id": "c2", "text": "B", "done_at": None}]})
    items = session.get(Task, "t1").checklist
    assert [i["done_at"] for i in items] == [STAMP, None]


def test_explicit_untick_and_a_tick_with_the_phones_time(session):
    ticked_task(session)
    call(session, "patch", {"checklist": [NEW_OPEN]})  # copyWith(clearDone: true).toJson()
    assert done_at(session) is None
    call(session, "patch", {"checklist": [{"id": "c1", "text": "A", "done_at": "2026-11-08T09:00:00.000Z"}]})
    assert done_at(session) == "2026-11-08T09:00:00Z"
