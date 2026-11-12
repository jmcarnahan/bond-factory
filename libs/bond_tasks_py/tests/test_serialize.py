import json
import re
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from conftest import NOW, Task

from bond_tasks_py import ITEM_KEYS, TaskCreate, service, task_item, task_items
from bond_tasks_py.timeutil import iso_z, parse_hhmm, parse_iso

FIXTURE = Path(__file__).resolve().parents[2].parent / "fixtures" / "tasks" / "task.json"


def row_from_wire(wire: dict) -> Task:
    """The stored row a wire item came from (the inverse of ``task_item``, which is what the fixture proves)."""
    stamp = lambda key: parse_iso(wire[key]) if wire[key] else None
    return Task(
        id=wire["id"], title=wire["title"], notes=wire["notes"], due_date=date.fromisoformat(wire["due_date"]) if wire["due_date"] else None,
        due_time=wire["due_time"], priority=wire.get("priority"), due_at=stamp("due_at") if "due_at" in wire else None,
        status=wire["status"], owner_user_id=wire["owner_user_id"],
        created_by=wire["owner_user_id"], assigned_user_id=wire["assigned_user_id"], checklist=wire["checklist"],
        remind_minutes_before=wire["remind_minutes_before"],
        links=wire["links"], completed_at=stamp("completed_at"),
        mirror_enabled=wire["mirror_enabled"], mirror_status=wire["mirror_status"],
        external_provider=wire["external_provider"], external_event_id=wire["external_event_id"],
        source=wire["source"], created_at=stamp("created_at"), updated_at=stamp("updated_at"),
    )


FIXTURES = ["task.json", "task_cancelled.json", "task_timed.json", "task_day_self.json",
            "task_day_other_null_due.json", "task_overdue.json"]
FIXTURE_NOW = datetime(2026, 3, 11, 20, 0)  # naive UTC; 13:00 on 2026-03-11 in America/Los_Angeles


def named(wire: dict) -> dict:
    names = {wire["owner_user_id"]: wire["owner_name"]}
    if wire["assigned_user_id"]:
        names[wire["assigned_user_id"]] = wire["assignee_name"]
    return names


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_round_trips_exactly_by_the_instant(name):
    wire = json.loads((FIXTURE.parent / name).read_text())
    assert task_item(row_from_wire(wire), today=date(2026, 3, 11), names=named(wire), now=FIXTURE_NOW) == wire



@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_has_exactly_the_item_keys(name):
    wire = json.loads((FIXTURE.parent / name).read_text())
    assert set(wire) == set(ITEM_KEYS) and len(wire) == 24


def test_old_shape_fixture_lacks_the_two_new_keys():
    wire = json.loads((FIXTURE.parent / "task_old_shape.json").read_text())
    assert set(wire) == set(ITEM_KEYS) - {"priority", "due_at"} and len(wire) == 22
    item = task_item(row_from_wire(wire), today=date(2026, 3, 11), names=named(wire), now=FIXTURE_NOW)
    assert item["priority"] is None and item["due_at"] is None


def test_the_timed_fixture_instant_is_the_zone_conversion():
    wire = json.loads((FIXTURE.parent / "task.json").read_text())
    local = datetime.combine(date.fromisoformat(wire["due_date"]), parse_hhmm(wire["due_time"]),
                             tzinfo=ZoneInfo("America/Los_Angeles"))
    assert iso_z(local) == wire["due_at"]


def test_the_date_only_fixture_is_end_of_day_in_the_owners_zone():
    wire = json.loads((FIXTURE.parent / "task_day_self.json").read_text())
    local = datetime.combine(date.fromisoformat(wire["due_date"]), time(17, 0), tzinfo=ZoneInfo("America/Los_Angeles"))
    assert iso_z(local) == wire["due_at"]
    assert json.loads((FIXTURE.parent / "task_day_other_null_due.json").read_text())["due_at"] is None


def test_today_summary_and_settings_fixtures_have_their_shapes():
    today = json.loads((FIXTURE.parent / "today.json").read_text())
    assert set(today) == {"overdue", "today", "undated", "done_today", "counts"}
    for key in ("overdue", "today", "undated", "done_today"):
        assert today[key] and today["counts"][key] == len(today[key])
        assert all(set(entry) == set(ITEM_KEYS) for entry in today[key])
    assert all(entry["overdue"] for entry in today["overdue"])
    assert not any(entry["overdue"] for key in ("today", "undated", "done_today") for entry in today[key])
    summary = json.loads((FIXTURE.parent / "summary.json").read_text())
    assert set(summary) == {"open", "overdue", "due_today", "no_date"} and all(type(v) is int for v in summary.values())
    settings = json.loads((FIXTURE.parent / "settings.json").read_text())
    assert settings == {"time_zone": "America/Los_Angeles", "start_of_day": "08:00", "end_of_day": "17:00",
                        "lead_minutes": 60, "warnings": [], "overridden": []}


def test_overdue_by_the_instant_needs_open_and_a_past_due_at(session):
    task = Task(owner_user_id="u1", created_by="u1", title="t", due_date=date(2026, 3, 11), due_time="09:00",
                due_at=datetime(2026, 3, 11, 16, 0), status="open")
    assert task_item(task, today=date(2026, 3, 11), now=datetime(2026, 3, 11, 16, 1))["overdue"] is True
    assert task_item(task, today=date(2026, 3, 11), now=datetime(2026, 3, 11, 16, 0))["overdue"] is False
    # the date alone would say not overdue (today is the due date): the instant decides
    assert task_item(task, today=date(2026, 3, 11), now=datetime(2026, 3, 11, 15, 0))["overdue"] is False
    task.status = "done"
    assert task_item(task, today=date(2026, 3, 12), now=datetime(2026, 3, 12))["overdue"] is False


def test_overdue_falls_back_to_the_date_when_due_at_is_not_computed(session):
    task = Task(owner_user_id="u1", created_by="u1", title="t", due_date=date(2026, 3, 10), status="open")
    assert task_item(task, today=date(2026, 3, 11), now=datetime(2026, 3, 11, 20, 0))["overdue"] is True
    assert task_item(task, today=date(2026, 3, 10), now=datetime(2026, 3, 10, 20, 0))["overdue"] is False


def test_an_undated_task_with_now_is_never_overdue():
    task = Task(owner_user_id="u1", created_by="u1", title="t", status="open")
    assert task_item(task, today=date(2030, 1, 1), now=datetime(2030, 1, 1))["overdue"] is False


def test_task_items_pass_now_through(session):
    task = Task(owner_user_id="u1", created_by="u1", title="t", due_date=date(2026, 3, 11), due_time="09:00",
                due_at=datetime(2026, 3, 11, 16, 0), status="open")
    assert task_items([task], today=date(2026, 3, 11), now=datetime(2026, 3, 11, 17, 0))[0]["overdue"] is True


def test_item_key_order_is_the_contract_order(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t"), now=NOW)
    assert list(task_item(task, today=date(2026, 11, 8), now=NOW)) == list(ITEM_KEYS)


def test_a_date_only_task_is_overdue_after_its_end_of_day_instant_and_not_when_done(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t", due_date=date(2026, 11, 7)), now=NOW)
    assert task_item(task, today=date(2026, 11, 8), now=NOW)["overdue"] is True
    assert task_item(task, today=date(2026, 11, 7), now=datetime(2026, 11, 7, 12, 0))["overdue"] is False
    service.complete(session, task, "u1", NOW)
    assert task_item(task, today=date(2026, 11, 8), now=NOW)["overdue"] is False


def test_an_undated_task_is_never_overdue(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t"), now=NOW)
    assert task_item(task, today=date(2030, 1, 1), now=datetime(2030, 1, 1))["overdue"] is False


def test_unknown_names_are_null_and_names_resolve_once(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t", assigned_user_id="u2"), now=NOW)
    calls = []

    def names(ids):
        calls.append(ids)
        return {"u1": "Ann"}

    items = task_items([task, task], today=date(2026, 11, 8), now=NOW, names=names)
    assert calls == [["u1", "u2"]]
    assert items[0]["owner_name"] == "Ann" and items[0]["assignee_name"] is None


def test_serialized_lists_are_copies(session):
    task = service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="t", checklist=[{"text": "a"}]), now=NOW)
    item = task_item(task, today=date(2026, 11, 8), now=NOW)
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
    assert item["remind_minutes_before"] >= -3
    assert item["priority"] in {None, 1, 2, 3}
    assert item["due_at"] is None or TIMESTAMP.match(item["due_at"])
    assert isinstance(item["overdue"], bool) and isinstance(item["mirror_enabled"], bool)
    for key in ("completed_at", "created_at", "updated_at"):
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
    check_wire_types(task_item(task, today=date(2026, 11, 8), now=NOW, names={"u1": "Ann", "u2": "Bo"}))
    service.complete(session, task, "u1", NOW)
    check_wire_types(task_item(task, today=date(2026, 11, 8), now=NOW))
