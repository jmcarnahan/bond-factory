from dataclasses import dataclass
from datetime import date, datetime

import pytest
from conftest import NOW, Task

from bond_tasks_py import TaskCreate, TaskError, service, sync_routes, verdict_for
from bond_tasks_py.models import USE_DEFAULT_REMINDER
from bond_tasks_py.sync_routes import NO_READS


@dataclass
class Op:
    id: str
    op: str
    action: str | None = None


@dataclass
class Ctx:
    user: object
    background: object = None


class Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append((fn, args))


def routes(**kw):
    return sync_routes(Task, now=lambda: NOW, **kw)


def call(route, session, user, op, data=None):
    return route.handler(session, Ctx(user), op, data or {})


def test_the_route_table_has_the_four_keys():
    table = routes()
    assert set(table) == {("tasks", None), ("tasks", "complete"), ("tasks", "reopen"), ("tasks", "cancel")}
    assert table[("tasks", None)].ops == frozenset({"put", "patch", "delete"})
    assert "title" in table[("tasks", None)].reads and "status" in table[("tasks", None)].reads


def test_put_creates_with_the_device_id_and_owner_from_the_session(session):
    call(routes()[("tasks", None)], session, "u1", Op("dev-1", "put"), {"title": "From phone", "notes": ""})
    task = session.get(Task, "dev-1")
    assert (task.owner_user_id, task.title, task.notes) == ("u1", "From phone", None)


def test_put_replay_by_the_owner_is_a_noop_and_foreign_id_conflicts(session):
    route = routes()[("tasks", None)]
    call(route, session, "u1", Op("dev-1", "put"), {"title": "A"})
    call(route, session, "u1", Op("dev-1", "put"), {"title": "B"})
    assert session.get(Task, "dev-1").title == "A"
    with pytest.raises(TaskError) as caught:
        call(route, session, "u2", Op("dev-1", "put"), {"title": "C"})
    assert caught.value.code == "id_taken"


def test_put_without_a_title_is_title_required(session):
    with pytest.raises(TaskError) as caught:
        call(routes()[("tasks", None)], session, "u1", Op("dev-2", "put"), {})
    assert caught.value.code == "title_required"


def test_patch_edits_and_clears_with_blank_strings(session):
    route = routes()[("tasks", None)]
    call(route, session, "u1", Op("t1", "put"), {"title": "A", "notes": "n", "due_date": date(2026, 11, 9)})
    call(route, session, "u1", Op("t1", "patch"), {"title": "B", "notes": "", "due_date": ""})
    task = session.get(Task, "t1")
    assert (task.title, task.notes, task.due_date) == ("B", None, None)


def test_patch_status_done_and_open(session):
    route = routes()[("tasks", None)]
    call(route, session, "u1", Op("t1", "put"), {"title": "A"})
    call(route, session, "u1", Op("t1", "patch"), {"status": "done"})
    assert session.get(Task, "t1").status == "done"
    call(route, session, "u1", Op("t1", "patch"), {"status": "open"})
    assert session.get(Task, "t1").status == "open"
    with pytest.raises(ValueError):
        call(route, session, "u1", Op("t1", "patch"), {"status": "cancelled"})


def test_patch_by_a_stranger_is_not_task_editor(session):
    route = routes()[("tasks", None)]
    call(route, session, "u1", Op("t1", "put"), {"title": "A"})
    with pytest.raises(TaskError) as caught:
        call(route, session, "u3", Op("t1", "patch"), {"title": "X"})
    assert caught.value.code == "not_task_editor"


def test_patch_of_a_missing_task_is_not_found(session):
    with pytest.raises(TaskError) as caught:
        call(routes()[("tasks", None)], session, "u1", Op("nope", "patch"), {"title": "X"})
    assert caught.value.code == "task_not_found"


def test_complete_and_reopen_actions(session):
    table = routes()
    call(table[("tasks", None)], session, "u1", Op("t1", "put"), {"title": "A"})
    call(table[("tasks", "complete")], session, "u1", Op("t1", "patch", "complete"))
    assert session.get(Task, "t1").status == "done"
    call(table[("tasks", "reopen")], session, "u1", Op("t1", "patch", "reopen"))
    assert session.get(Task, "t1").status == "open"


def test_delete_is_hard_idempotent_and_owner_only(session):
    route = routes()[("tasks", None)]
    call(route, session, "u1", Op("t1", "put"), {"title": "A", "assigned_user_id": "u2"})
    with pytest.raises(TaskError) as caught:
        call(route, session, "u2", Op("t1", "delete"))
    assert caught.value.code == "not_task_owner"
    call(route, session, "u1", Op("t1", "delete"))
    assert session.get(Task, "t1") is None
    call(route, session, "u1", Op("t1", "delete"))  # replayed delete: success


def test_hooks_get_the_context_and_the_pointer(session):
    seen = []
    removed = []
    table = routes(after_write=lambda ctx, s, t: seen.append(t.id),
                   after_delete=lambda ctx, s, pointer: removed.append(pointer))
    route = table[("tasks", None)]
    call(route, session, "u1", Op("t1", "put"), {"title": "A"})
    session.get(Task, "t1").external_event_id = "ev-1"
    call(route, session, "u1", Op("t1", "delete"))
    assert seen == ["t1"] and removed[0].event_id == "ev-1"


def test_user_exists_guards_the_assignee(session):
    route = routes(user_exists={"u1"}.__contains__)[("tasks", None)]
    with pytest.raises(TaskError) as caught:
        call(route, session, "u1", Op("t1", "put"), {"title": "A", "assigned_user_id": "ghost"})
    assert caught.value.code == "unknown_assignee"


def test_ctx_user_may_be_an_object(session):
    @dataclass
    class U:
        user_id: str

    call(routes()[("tasks", None)], session, U("u9"), Op("t1", "put"), {"title": "A"})
    assert session.get(Task, "t1").owner_user_id == "u9"


def test_verdict_mapping():
    assert verdict_for(TaskError("not_task_editor")) == ("forbidden", "not_task_editor")
    assert verdict_for(TaskError("not_task_owner")) == ("forbidden", "not_task_owner")
    assert verdict_for(TaskError("task_not_found")) == ("not_found", "task_not_found")
    assert verdict_for(TaskError("id_taken")) == ("conflict", "id_taken")
    assert verdict_for(TaskError("title_required")) == ("invalid", "title_required")
    assert verdict_for(ValueError("x")) is None


def test_service_still_importable_next_to_routes():
    assert service.get is not None


def test_put_keeps_the_source_and_a_patch_cannot_change_it(session):
    route = routes()[("tasks", None)]
    assert "source" in route.reads
    call(route, session, "u1", Op("d1", "put"), {"title": "A", "source": "capture"})
    assert session.get(Task, "d1").source == "capture"
    call(route, session, "u1", Op("d1", "patch"), {"source": "manual", "title": "B"})
    task = session.get(Task, "d1")
    assert (task.source, task.title) == ("capture", "B")


def test_a_patch_clearing_the_date_clears_the_time_and_due_at(session):
    route = routes()[("tasks", None)]
    call(route, session, "u1", Op("d1", "put"), {"title": "A", "due_date": "2026-11-09", "due_time": "09:30"})
    assert session.get(Task, "d1").due_at is not None
    call(route, session, "u1", Op("d1", "patch"), {"due_date": None})
    task = session.get(Task, "d1")
    assert (task.due_date, task.due_time, task.due_at) == (None, None, None)


def test_complete_and_cancel_are_idempotent_and_change_no_stamps(session):
    table = routes()
    call(table[("tasks", None)], session, "u1", Op("d1", "put"), {"title": "A"})
    task = session.get(Task, "d1")
    service.complete(session, task, "u1", NOW)
    stamps = (task.completed_at, task.updated_at)
    later = datetime(2030, 1, 1)
    service.complete(session, task, "u1", later)
    assert (task.completed_at, task.updated_at) == stamps
    service.cancel(session, task, "u1", NOW)
    stamps = (task.completed_at, task.updated_at)
    service.cancel(session, task, "u1", later)
    assert (task.status, task.completed_at, task.updated_at) == ("cancelled", *stamps)


def test_fields_and_reads_carry_priority_and_due_at():
    from bond_tasks_py.sync_routes import FIELDS, READS

    assert {"priority", "due_at"} <= set(FIELDS) and {"priority", "due_at"} <= set(READS)


def test_put_stores_priority_and_a_plausible_due_at_hint(session):
    data = {"title": "A", "due_date": "2026-11-09", "due_time": "09:30", "priority": 3,
            "due_at": "2026-11-09T14:30:00Z"}
    call(routes()[("tasks", None)], session, "u1", Op("d1", "put"), data)
    task = session.get(Task, "d1")
    assert task.priority == 3 and task.due_at == datetime(2026, 11, 9, 14, 30)


def test_a_bad_or_inconsistent_due_at_never_raises(session):
    route = routes()[("tasks", None)]
    for n, bad in enumerate(("garbage", 12, "", "2026-11-09T14:37:00Z", "0001-01-01T00:00:00Z", None)):
        data = {"title": "A", "due_date": "2026-11-09", "due_time": "09:30", "due_at": bad}
        call(route, session, "u1", Op(f"d{n}", "put"), data)
        assert session.get(Task, f"d{n}").due_at == datetime(2026, 11, 9, 9, 30)  # computed in the app zone (UTC)
    call(route, session, "u1", Op("d0", "patch"), {"due_time": "10:00", "due_at": "nonsense"})
    assert session.get(Task, "d0").due_at == datetime(2026, 11, 9, 10, 0)


def test_a_plausible_hint_is_kept_even_when_the_writer_has_a_stored_zone(session):
    table = routes(zone_of=lambda ctx, sess, user_id: "America/New_York")
    data = {"title": "A", "due_date": "2026-03-12", "due_time": "09:00", "due_at": "2026-03-12T16:00:00Z"}
    call(table[("tasks", None)], session, "u1", Op("d1", "put"), data)
    assert session.get(Task, "d1").due_at == datetime(2026, 3, 12, 16, 0)  # not New York's 13:00Z
    call(table[("tasks", None)], session, "u1", Op("d1", "patch"),
         {"due_time": "10:00", "due_at": "2026-03-12T17:00:00Z"})
    assert session.get(Task, "d1").due_at == datetime(2026, 3, 12, 17, 0)


def test_a_patch_with_only_a_hint_writes_nothing(session):
    call(routes()[("tasks", None)], session, "u1", Op("d1", "put"), {"title": "A", "due_date": "2026-11-09"})
    task = session.get(Task, "d1")
    task.mirror_status = "mirrored"
    before = (task.updated_at, task.mirror_status, task.due_at)
    later = sync_routes(Task, now=lambda: datetime(2030, 1, 1))[("tasks", None)]
    call(later, session, "u1", Op("d1", "patch"), {"due_at": "2026-11-09T14:30:00Z"})
    assert (task.updated_at, task.mirror_status, task.due_at) == before


def test_service_create_has_no_permissions_parameter(session):
    with pytest.raises(TypeError):
        service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                       data=TaskCreate(title="A"), now=NOW, permissions=object())


def test_delete_removes_the_link_index_rows_in_the_same_flush(session):
    from conftest import LinkIndex

    table = sync_routes(Task, now=lambda: NOW, link_index_model=LinkIndex)
    route = table[("tasks", None)]
    call(route, session, "u1", Op("d1", "put"), {"title": "A"})
    call(route, session, "u1", Op("d2", "put"), {"title": "B"})
    session.add_all([LinkIndex(task_id="d1", kind="contact", ref_id="c1"),
                     LinkIndex(task_id="d2", kind="contact", ref_id="c1")])
    session.flush()
    call(route, session, "u1", Op("d1", "delete"))
    assert [row.task_id for row in session.query(LinkIndex).all()] == ["d2"]
    service.delete(session, session.get(Task, "d2"), "u1", link_index_model=LinkIndex)
    assert session.query(LinkIndex).count() == 0


def test_delete_without_the_index_model_leaves_rows_alone(session):
    from conftest import LinkIndex

    call(routes()[("tasks", None)], session, "u1", Op("d1", "put"), {"title": "A"})
    session.add(LinkIndex(task_id="d1", kind="contact", ref_id="c1"))
    session.flush()
    call(routes()[("tasks", None)], session, "u1", Op("d1", "delete"))
    assert session.query(LinkIndex).count() == 1


def test_a_due_at_whose_parsing_overflows_is_dropped_never_raised(session):
    route = routes()[("tasks", None)]
    for n, bad in enumerate(("0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-12:00")):
        data = {"title": "A", "due_date": "2026-11-09", "due_time": "09:30", "due_at": bad}
        call(route, session, "u1", Op(f"o{n}", "put"), data)
        assert session.get(Task, f"o{n}").due_at == datetime(2026, 11, 9, 9, 30)


def test_zone_of_supplies_the_writers_stored_zone(session):
    seen = []

    def zone_of(ctx, sess, user_id):
        seen.append(user_id)
        return "America/New_York"

    call(routes(zone_of=zone_of)[("tasks", None)], session, "u1", Op("d1", "put"),
         {"title": "A", "due_date": "2026-11-09", "due_time": "09:30"})
    assert seen == ["u1"] and session.get(Task, "d1").due_at == datetime(2026, 11, 9, 14, 30)  # EST


def test_the_cancel_route_cancels_for_the_owner_only(session):
    table = routes()
    call(table[("tasks", None)], session, "u1", Op("d1", "put"), {"title": "A"})
    session.get(Task, "d1").assigned_user_id = "u2"
    with pytest.raises(TaskError) as caught:
        call(table[("tasks", "cancel")], session, "u2", Op("d1", "patch"))
    assert caught.value.code == "not_task_owner"
    call(table[("tasks", "cancel")], session, "u1", Op("d1", "patch"))
    assert session.get(Task, "d1").status == "cancelled"


def test_permissions_and_link_hook_are_passed_down(session):
    from support_core import CoOfficer

    hooked = []
    table = routes(permissions=CoOfficer(), link_hook=lambda sess, task: hooked.append(task.id))
    call(table[("tasks", None)], session, "u1", Op("d1", "put"), {"title": "A"})
    call(table[("tasks", None)], session, "u3", Op("d1", "patch"), {"title": "B"})  # u3 may edit under the policy
    assert session.get(Task, "d1").title == "B" and hooked == ["d1", "d1"]


def test_on_deleted_gets_the_id_and_owner_even_without_a_mirror(session):
    seen = []
    route = routes(on_deleted=lambda ctx, s, task_id, owner: seen.append((task_id, owner)))[("tasks", None)]
    call(route, session, "u1", Op("t1", "put"), {"title": "A"})
    call(route, session, "u1", Op("t1", "delete"))
    call(route, session, "u1", Op("t1", "delete"))  # already gone: no second call
    assert seen == [("t1", "u1")]


@pytest.mark.parametrize("priority", [0, 7])
def test_a_priority_outside_one_to_three_is_invalid_priority_on_put_and_patch(session, priority):
    route = routes()[("tasks", None)]
    with pytest.raises(TaskError) as caught:
        call(route, session, "u1", Op("t9", "put"), {"title": "A", "priority": priority})
    assert caught.value.code == "invalid_priority" and caught.value.status == 422
    call(route, session, "u1", Op("t1", "put"), {"title": "A"})
    with pytest.raises(TaskError) as caught:
        call(route, session, "u1", Op("t1", "patch"), {"priority": priority})
    assert caught.value.code == "invalid_priority"


def test_an_unparseable_due_at_is_ignored_like_a_wrong_hint_on_put_and_patch(session):
    route = routes()[("tasks", None)]
    for n, bad in enumerate(("garbage", 12345, 1.5, ["x"], {"a": 1}, 10**30)):
        data = {"title": "A", "due_date": "2026-11-09", "due_time": "09:30", "due_at": bad}
        call(route, session, "u1", Op(f"g{n}", "put"), data)
        assert session.get(Task, f"g{n}").due_at == datetime(2026, 11, 9, 9, 30)
        call(route, session, "u1", Op(f"g{n}", "patch"), {"due_time": "11:00", "due_at": bad})
        assert session.get(Task, f"g{n}").due_at == datetime(2026, 11, 9, 11, 0)


def test_the_closing_routes_read_no_data_and_the_task_route_lists_its_optional_keys():
    table = routes()
    for action in ("complete", "reopen", "cancel"):
        assert table[("tasks", action)].reads == NO_READS and table[("tasks", action)].optional == ()
    route = table[("tasks", None)]
    assert set(route.optional) == {"due_at", "priority", "remind_minutes_before"} and set(route.optional) <= set(route.reads)
    assert set(routes(fields=["title", "priority"])[("tasks", None)].optional) == {"priority"}


@pytest.mark.parametrize("blank", ["", "  "])
def test_a_blank_priority_or_reminder_is_not_sent_on_put_and_patch(session, blank):
    route = routes()[("tasks", None)]
    call(route, session, "u1", Op("b1", "put"), {"title": "A", "priority": blank, "remind_minutes_before": blank})
    task = session.get(Task, "b1")
    assert task.priority is None and task.remind_minutes_before == USE_DEFAULT_REMINDER
    call(route, session, "u1", Op("b1", "patch"), {"priority": 3, "remind_minutes_before": 15})
    call(route, session, "u1", Op("b1", "patch"), {"title": "B", "priority": blank, "remind_minutes_before": blank})
    assert (task.title, task.priority, task.remind_minutes_before) == ("B", 3, 15)  # a blank changes nothing


def test_a_priority_that_is_not_blank_is_still_checked(session):
    route = routes()[("tasks", None)]
    with pytest.raises(TaskError) as caught:
        call(route, session, "u1", Op("b2", "put"), {"title": "A", "priority": 9})
    assert caught.value.code == "invalid_priority"


def test_the_closing_routes_name_no_key_a_payload_can_carry():
    """`()` would mean "coerce every key" to the sync dispatcher, so the reads must be non-empty AND match nothing."""
    payload = {"status", "completed_at", "completed_by", "mirror_status", "updated_at", "created_at", "title", "due_at"}
    columns = set(Task.__table__.columns.keys())
    for action in ("complete", "reopen", "cancel"):
        reads = routes()[("tasks", action)].reads
        assert reads and not set(reads) & (columns | payload)
