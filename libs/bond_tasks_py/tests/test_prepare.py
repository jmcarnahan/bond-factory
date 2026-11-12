"""The ``prepare`` hook on create, update and the sync routes, and ``fields`` on ``sync_routes``."""

from dataclasses import dataclass

import pytest
from conftest import NOW
from support_core import HostTask

from bond_tasks_py import TaskCreate, TaskError, TaskUpdate, service, sync_routes

COLUMNS = ("contact_id", "loan_id", "external_ref")


@dataclass
class Op:
    id: str
    op: str


@dataclass
class Ctx:
    user: str


def make(session, **kw):
    return service.create(session, task_model=HostTask, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="A"), now=NOW, host_columns=COLUMNS, **kw)


def edit(session, task, actor="u1", **kw):
    return service.update(session, task=task, actor_user_id=actor, data=TaskUpdate(title="B"), now=NOW,
                          host_columns=COLUMNS, **kw)


def test_prepare_sees_old_task_and_new_extras(host_session):
    session = host_session
    task = make(session, extras={"contact_id": "c1"})
    seen = []

    def prepare(sess, stored, actor, extras):
        seen.append((sess is session, stored and stored.title, stored and stored.contact_id, actor, dict(extras)))
        return extras

    edit(session, task, extras={"contact_id": "c2"}, prepare=prepare)
    assert seen == [(True, "A", "c1", "u1", {"contact_id": "c2"})]  # before any field changed
    assert (task.title, task.contact_id) == ("B", "c2")
    seen.clear()
    make(session, extras={"loan_id": "l1"}, prepare=prepare)
    assert seen == [(True, None, None, "u1", {"loan_id": "l1"})]  # no stored task on create


def test_prepare_can_refuse_before_any_write(host_session):
    session = host_session
    task = make(session, extras={"contact_id": "c1"})
    session.flush()

    def refuse(sess, stored, actor, extras):
        raise TaskError("relink_needs_owner", "No.", 403)

    with pytest.raises(TaskError) as caught:
        edit(session, task, extras={"contact_id": "c2"}, prepare=refuse)
    assert caught.value.code == "relink_needs_owner"
    assert (task.title, task.contact_id) == ("A", "c1") and task not in session.dirty
    with pytest.raises(TaskError):
        make(session, prepare=refuse)
    assert session.query(HostTask).count() == 1


def test_prepare_derives_extra_column(host_session):
    session = host_session
    task = make(session, extras={"loan_id": "l9"},
                prepare=lambda s, t, a, extras: {**extras, "external_ref": "ref-" + extras["loan_id"]})
    assert (task.loan_id, task.external_ref) == ("l9", "ref-l9")
    edit(session, task, extras={"loan_id": "l10"},
         prepare=lambda s, t, a, extras: {**extras, "external_ref": "ref-" + extras["loan_id"]})
    assert task.external_ref == "ref-l10"


def test_prepare_none_unchanged(host_session):
    session = host_session
    task = make(session, extras={"contact_id": "c1", "evil": "x"})
    assert task.contact_id == "c1"
    edit(session, task, extras={"contact_id": "c2"})
    assert task.contact_id == "c2"


def test_prepare_through_sync_routes_put_and_patch(host_session):
    session = host_session
    calls = []

    def prepare(sess, stored, actor, extras):
        calls.append((stored.title if stored is not None else None, actor, dict(extras)))
        if extras.get("loan_id") == "bad":
            raise TaskError("bad_loan")
        return extras

    route = sync_routes(HostTask, now=lambda: NOW, host_columns=COLUMNS, prepare=prepare)[("tasks", None)]
    route.handler(session, Ctx("u1"), Op("t1", "put"), {"title": "A", "loan_id": "l1"})
    route.handler(session, Ctx("u1"), Op("t1", "patch"), {"loan_id": "l2"})
    assert calls == [(None, "u1", {"loan_id": "l1"}), ("A", "u1", {"loan_id": "l2"})]
    assert session.get(HostTask, "t1").loan_id == "l2"
    with pytest.raises(TaskError) as caught:
        route.handler(session, Ctx("u1"), Op("t1", "patch"), {"loan_id": "bad"})
    assert caught.value.code == "bad_loan" and session.get(HostTask, "t1").loan_id == "l2"


def test_fields_narrows_what_a_device_may_write(host_session):
    session = host_session
    table = sync_routes(HostTask, now=lambda: NOW, fields=("title", "notes"))
    route = table[("tasks", None)]
    assert "title" in route.reads and "priority" not in route.reads and "status" in route.reads
    route.handler(session, Ctx("u1"), Op("t1", "put"), {"title": "A", "priority": 3, "notes": "n"})
    task = session.get(HostTask, "t1")
    assert (task.title, task.notes, task.priority) == ("A", "n", None)
    route.handler(session, Ctx("u1"), Op("t1", "patch"), {"priority": 2, "title": "B"})
    assert (task.title, task.priority) == ("B", None)
    default = sync_routes(HostTask, now=lambda: NOW)[("tasks", None)]
    default.handler(session, Ctx("u1"), Op("t2", "put"), {"title": "C", "priority": 3})
    assert session.get(HostTask, "t2").priority == 3


def test_fields_with_a_name_outside_the_device_set_is_a_programming_error():
    with pytest.raises(ValueError):
        sync_routes(HostTask, fields=("title", "owner_user_id"))
