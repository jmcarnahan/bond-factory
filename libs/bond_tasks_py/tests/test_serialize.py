import json
import re
from datetime import date
from pathlib import Path

import pytest
from conftest import NOW, Task

from bond_tasks_py import ITEM_KEYS, TaskCreate, service, task_item, task_items
from bond_tasks_py.timeutil import parse_iso

FIXTURE = Path(__file__).resolve().parents[2].parent / "fixtures" / "tasks" / "task.json"


def row_from_wire(wire: dict) -> Task:
    """The stored row a wire item came from (the inverse of ``task_item``, which is what the fixture proves)."""
    stamp = lambda key: parse_iso(wire[key]) if wire[key] else None
    return Task(
        id=wire["id"], title=wire["title"], notes=wire["notes"], due_date=date.fromisoformat(wire["due_date"]) if wire["due_date"] else None,
        due_time=wire["due_time"], status=wire["status"], owner_user_id=wire["owner_user_id"],
        created_by=wire["owner_user_id"], assigned_user_id=wire["assigned_user_id"], checklist=wire["checklist"],
        remind_minutes_before=wire["remind_minutes_before"], remind_at=stamp("remind_at"),
        reminded_at=stamp("reminded_at"), links=wire["links"], completed_at=stamp("completed_at"),
        mirror_enabled=wire["mirror_enabled"], mirror_status=wire["mirror_status"],
        external_provider=wire["external_provider"], external_event_id=wire["external_event_id"],
        source=wire["source"], created_at=stamp("created_at"), updated_at=stamp("updated_at"),
    )


FIXTURES = ["task.json", "task_cancelled.json"]


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_round_trips_exactly(name):
    wire = json.loads((FIXTURE.parent / name).read_text())
    names = {wire["owner_user_id"]: wire["owner_name"]}
    if wire["assigned_user_id"]:
        names[wire["assigned_user_id"]] = wire["assignee_name"]
    assert task_item(row_from_wire(wire), today=date(2026, 3, 11), names=names) == wire


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_has_exactly_the_item_keys(name):
    assert set(json.loads((FIXTURE.parent / name).read_text())) == set(ITEM_KEYS)


def test_item_key_order_is_the_contract_order(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t"), now=NOW)
    assert list(task_item(task, today=date(2026, 11, 8))) == list(ITEM_KEYS)


def test_overdue_is_open_and_before_the_clients_today(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t", due_date=date(2026, 11, 7)), now=NOW)
    assert task_item(task, today=date(2026, 11, 8))["overdue"] is True
    assert task_item(task, today=date(2026, 11, 7))["overdue"] is False
    assert task_item(task, today=date(2026, 11, 6))["overdue"] is False
    service.complete(session, task, "u1", NOW)
    assert task_item(task, today=date(2026, 11, 8))["overdue"] is False


def test_an_undated_task_is_never_overdue(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t"), now=NOW)
    assert task_item(task, today=date(2030, 1, 1))["overdue"] is False


def test_unknown_names_are_null_and_names_resolve_once(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t", assigned_user_id="u2"), now=NOW)
    calls = []

    def names(ids):
        calls.append(ids)
        return {"u1": "Ann"}

    items = task_items([task, task], today=date(2026, 11, 8), names=names)
    assert calls == [["u1", "u2"]]
    assert items[0]["owner_name"] == "Ann" and items[0]["assignee_name"] is None


def test_serialized_lists_are_copies(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t", checklist=[{"text": "a"}]), now=NOW)
    item = task_item(task, today=date(2026, 11, 8))
    item["checklist"][0]["text"] = "changed"
    assert task.checklist[0]["text"] == "a"


TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def check_wire_types(item: dict) -> None:
    assert isinstance(item["id"], str) and isinstance(item["title"], str)
    assert item["notes"] is None or isinstance(item["notes"], str)
    assert item["due_date"] is None or date.fromisoformat(item["due_date"]).isoformat() == item["due_date"]
    assert item["due_time"] is None or re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", item["due_time"])
    assert item["status"] in {"open", "done", "cancelled"}
    assert item["mirror_status"] in {"pending", "mirrored", "skipped", "failed"}
    assert item["external_provider"] in {None, "google", "microsoft"}
    assert isinstance(item["remind_minutes_before"], int) and not isinstance(item["remind_minutes_before"], bool)
    assert item["remind_minutes_before"] >= -2
    assert isinstance(item["overdue"], bool) and isinstance(item["mirror_enabled"], bool)
    for key in ("remind_at", "reminded_at", "completed_at", "created_at", "updated_at"):
        assert item[key] is None or TIMESTAMP.match(item[key]), key
    for key in ("owner_user_id", "owner_name", "assigned_user_id", "assignee_name", "external_event_id"):
        assert item[key] is None or isinstance(item[key], str), key
    assert isinstance(item["source"], str)
    for entry in item["checklist"]:
        assert set(entry) == {"id", "text", "done_at"}
        assert isinstance(entry["id"], str) and isinstance(entry["text"], str)
        assert entry["done_at"] is None or TIMESTAMP.match(entry["done_at"])
    for link in item["links"]:
        assert set(link) == {"kind", "id", "label"} and isinstance(link["kind"], str) and isinstance(link["id"], str)


@pytest.mark.parametrize("name", FIXTURES)
def test_the_fixtures_themselves_have_the_wire_types(name):
    check_wire_types(json.loads((FIXTURE.parent / name).read_text()))


def test_a_served_item_has_the_wire_types(session):
    task = service.create(
        session, task_model=Task, owner_user_id="u1", actor_user_id="u1", now=NOW,
        data=TaskCreate(title="t", due_date=date(2026, 11, 9), due_time="09:30", remind_minutes_before=15,
                        assigned_user_id="u2", checklist=[{"text": "a", "done": True}, {"text": "b"}],
                        links=[{"kind": "loan", "id": "L1", "label": "One"}]))
    check_wire_types(task_item(task, today=date(2026, 11, 8), names={"u1": "Ann", "u2": "Bo"}))
    service.complete(session, task, "u1", NOW)
    check_wire_types(task_item(task, today=date(2026, 11, 8)))
