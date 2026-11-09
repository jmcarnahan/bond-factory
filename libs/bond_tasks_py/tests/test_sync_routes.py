from dataclasses import dataclass
from datetime import date

import pytest
from conftest import NOW, FakeScheduler, Task

from bond_tasks_py import TaskError, service, sync_routes, verdict_for


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
    assert set(table) == {("tasks", None), ("tasks", "complete"), ("tasks", "reopen")}
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


def test_scheduler_follows_writes_and_deletes(session):
    scheduler = FakeScheduler()
    route = routes(scheduler=scheduler)[("tasks", None)]
    data = {"title": "A", "due_date": date(2026, 11, 9), "due_time": "10:00", "remind_minutes_before": 0}
    call(route, session, "u1", Op("t1", "put"), data)
    assert "task_reminder:t1" in scheduler.jobs
    call(route, session, "u1", Op("t1", "delete"))
    assert scheduler.jobs == {}


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
