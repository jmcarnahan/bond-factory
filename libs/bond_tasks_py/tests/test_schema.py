"""The table, pinned literally, and the JSON shapes."""

import pytest
from conftest import NOW, Task
from pydantic import ValidationError
from sqlalchemy import inspect

from bond_tasks_py import ITEM_KEYS, TASK_COLUMNS, ChecklistInput, TaskCreate, TaskUpdate
from bond_tasks_py.schema import normalize_checklist

LITERAL_COLUMNS = [
    "id", "owner_user_id", "created_by", "assigned_user_id", "title", "notes", "due_date", "due_time", "priority",
    "due_at", "status", "completed_at", "completed_by", "checklist", "remind_minutes_before",
    "mirror_enabled", "mirror_status", "external_provider", "external_event_id", "external_account_user_id",
    "external_etag", "links", "source", "created_at", "updated_at",
]


def test_columns_are_pinned_literally():
    assert list(Task.__table__.c.keys()) == LITERAL_COLUMNS
    assert list(TASK_COLUMNS) == LITERAL_COLUMNS


def test_nullability_matches_the_contract():
    assert {c.name: c.nullable for c in Task.__table__.c} == TASK_COLUMNS


def test_table_name_and_composite_indexes():
    assert Task.__tablename__ == "tasks"
    composite = {ix.name: [c.name for c in ix.columns] for ix in Task.__table__.indexes if len(ix.columns) > 1}
    assert composite == {
        "ix_tasks_owner_status_due": ["owner_user_id", "status", "due_date"],
        "ix_tasks_assignee_status_due": ["assigned_user_id", "status", "due_date"],
        "ix_tasks_status_due_at": ["status", "due_at"],
    }


def test_single_column_indexes_exist(factory):
    names = {ix["name"] for ix in inspect(factory.kw["bind"]).get_indexes("tasks")}
    assert {"ix_tasks_owner_user_id", "ix_tasks_assigned_user_id", "ix_tasks_due_date"} <= names


def test_defaults_on_insert(session):
    task = Task(owner_user_id="u1", created_by="u1", title="x")
    session.add(task)
    session.flush()
    assert (task.status, task.remind_minutes_before, task.mirror_enabled, task.mirror_status, task.source) == (
        "open", -3, True, "pending", "manual")
    assert task.checklist == [] and task.links == [] and task.id


def test_item_keys_are_the_contract_list():
    assert len(ITEM_KEYS) == 24 and ITEM_KEYS[0] == "id" and ITEM_KEYS[-1] == "overdue"


def test_client_chosen_id_pattern():
    assert TaskCreate(id="a-b_9").id == "a-b_9"
    for bad in ("", "a b", "x" * 65, "a/b", "caf\u00e9", "\u0663"):
        with pytest.raises(ValidationError):
            TaskCreate(id=bad)


def test_due_time_pattern():
    assert TaskCreate(due_time="09:30").due_time == "09:30"
    for bad in ("9:30", "24:00", "09:60", "0930"):
        with pytest.raises(ValidationError):
            TaskCreate(due_time=bad)


def test_remind_minutes_range():
    for ok in (-3, -2, -1, 0, 15, 10080, 525600):
        assert TaskCreate(remind_minutes_before=ok).remind_minutes_before == ok
    for bad in (-4, 525601):
        with pytest.raises(ValidationError):
            TaskCreate(remind_minutes_before=bad)


def test_update_tracks_what_was_sent():
    data = TaskUpdate.model_validate({"notes": None, "title": "t"})
    assert data.model_fields_set == {"notes", "title"}
    with pytest.raises(ValidationError):
        TaskUpdate.model_validate({"mirror_enabled": None})


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        TaskCreate.model_validate({"title": "x", "owner_user_id": "other"})


def test_checklist_items_get_ids_and_done_stamps():
    items = normalize_checklist(
        [ChecklistInput(text=" a "), ChecklistInput(text="b", done=True)], existing=None, now=NOW)
    assert [i["text"] for i in items] == ["a", "b"]
    assert items[0]["done_at"] is None and items[1]["done_at"] == "2026-11-08T12:00:00Z"
    assert items[0]["id"] != items[1]["id"]


def test_checklist_keeps_done_at_by_id_and_untick_clears():
    first = normalize_checklist([ChecklistInput(text="a", done=True)], existing=None, now=NOW)
    keep = normalize_checklist([ChecklistInput(id=first[0]["id"], text="a2")], existing=first, now=NOW)
    assert keep[0]["done_at"] == first[0]["done_at"] and keep[0]["text"] == "a2"
    cleared = normalize_checklist([ChecklistInput(id=first[0]["id"], text="a", done=False)], existing=first, now=NOW)
    assert cleared[0]["done_at"] is None


def test_blank_checklist_text_is_refused():
    with pytest.raises(ValidationError):
        ChecklistInput(text="   ")


def test_repeated_checklist_ids_are_reminted():
    items = normalize_checklist([ChecklistInput(id="x", text="a"), ChecklistInput(id="x", text="b")],
                                existing=None, now=NOW)
    assert items[0]["id"] == "x" and items[1]["id"] != "x"


def test_nul_bytes_are_refused_everywhere():
    for build in (
        lambda: TaskCreate(title="a\x00b"), lambda: TaskCreate(title="t", notes="n\x00"),
        lambda: TaskCreate(title="t", assigned_user_id="u\x00"),
        lambda: TaskCreate(title="t", checklist=[{"text": "x\x00"}]),
        lambda: TaskCreate(title="t", links=[{"kind": "a", "id": "b", "label": "l\x00"}]),
        lambda: TaskUpdate.model_validate({"title": "\x00"}),
    ):
        with pytest.raises(ValidationError):
            build()


def test_priority_is_one_to_three_and_null_clears_on_update():
    assert TaskCreate(priority=3).priority == 3
    for bad in (0, 4, -1):
        with pytest.raises(ValidationError):
            TaskCreate(priority=bad)
    assert TaskUpdate.model_validate({"priority": None}).model_fields_set == {"priority"}


def test_due_at_and_time_zone_are_accepted_as_hints():
    data = TaskCreate(due_at="2026-03-12T16:30:00Z", time_zone="America/Los_Angeles")
    assert data.due_at is not None and data.time_zone == "America/Los_Angeles"
    with pytest.raises(ValidationError):
        TaskCreate(time_zone="x" * 65)


def test_only_five_update_fields_accept_null():
    for field in ("due_date", "due_time", "priority", "assigned_user_id", "notes", "title"):
        assert TaskUpdate.model_validate({field: None}).model_fields_set == {field}
    for field in ("checklist", "links", "remind_minutes_before", "mirror_enabled"):
        with pytest.raises(ValidationError):
            TaskUpdate.model_validate({field: None})


def test_duplicate_links_keep_the_first():
    from bond_tasks_py.schema import LinkInput, normalize_links

    links = normalize_links([LinkInput(kind="contact", id="c1", label="First"),
                             LinkInput(kind="contact", id="c2"),
                             LinkInput(kind="contact", id="c1", label="Second"),
                             LinkInput(kind="loan", id="c1")])
    assert [(x["kind"], x["id"], x["label"]) for x in links] == [
        ("contact", "c1", "First"), ("contact", "c2", None), ("loan", "c1", None)]


def test_new_error_codes_are_422_with_messages():
    from bond_tasks_py import CODES, TaskError

    for code in ("invalid_time_zone", "invalid_priority"):
        assert CODES[code][0] == 422 and CODES[code][1]
        err = TaskError(code)
        assert err.status == 422 and err.code == code and err.message == CODES[code][1]


def test_a_new_task_schema_defaults_to_use_my_default():
    assert TaskCreate(title="x").remind_minutes_before == -3
    assert TaskCreate(title="x", remind_minutes_before=-2).remind_minutes_before == -2


@pytest.mark.parametrize("bad", ["garbage", 12345, ["x"], {"a": 1}, "", 10**30])
def test_an_unparseable_due_at_hint_is_dropped_not_rejected(bad):
    assert TaskCreate(title="x", due_at=bad).due_at is None
    assert TaskUpdate(due_at=bad).due_at is None
    assert TaskCreate(title="x", due_at="2026-11-09T14:30:00Z").due_at is not None
