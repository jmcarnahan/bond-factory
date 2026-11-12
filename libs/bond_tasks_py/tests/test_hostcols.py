"""App columns survive create, update and sync; bond stores only what the allow-list names."""

from dataclasses import dataclass
from datetime import date

import pytest
from conftest import NOW
from support_core import HostTask

from bond_tasks_py import TaskCreate, TaskUpdate, service, sync_routes
from bond_tasks_py.hostcols import apply_extras

COLUMNS = ("contact_id", "loan_id", "external_ref")


@dataclass
class Op:
    id: str
    op: str


@dataclass
class Ctx:
    user: str


def test_apply_extras_sets_only_named_keys_and_ignores_the_rest():
    task = HostTask()
    apply_extras(task, {"contact_id": "c1", "title": "hijack", "other": 1}, ("contact_id",))
    assert task.contact_id == "c1" and task.title is None and task.loan_id is None


def test_apply_extras_with_nothing_is_a_noop_and_none_clears():
    task = HostTask(contact_id="c1")
    apply_extras(task, None, COLUMNS)
    apply_extras(task, {}, COLUMNS)
    assert task.contact_id == "c1"
    apply_extras(task, {"contact_id": None}, COLUMNS)
    assert task.contact_id is None


def test_a_host_column_the_model_lacks_is_a_programming_error():
    with pytest.raises(ValueError, match="no_such_column"):
        apply_extras(HostTask(), {}, ("contact_id", "no_such_column"))


def test_extras_survive_create_and_update(host_session):
    task = service.create(host_session, task_model=HostTask, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="Call", due_date=date(2026, 3, 12)), now=NOW,
                          extras={"contact_id": "c1", "loan_id": "l1", "evil": "x"}, host_columns=COLUMNS)
    host_session.expire_all()
    stored = host_session.get(HostTask, task.id)
    assert (stored.contact_id, stored.loan_id, stored.external_ref) == ("c1", "l1", None)
    service.update(host_session, task=stored, actor_user_id="u1", data=TaskUpdate(title="Call 2"), now=NOW,
                   extras={"loan_id": "l2", "external_ref": "r9"}, host_columns=COLUMNS)
    host_session.expire_all()
    stored = host_session.get(HostTask, task.id)
    assert (stored.title, stored.contact_id, stored.loan_id, stored.external_ref) == ("Call 2", "c1", "l2", "r9")


def test_sync_put_and_patch_carry_the_app_columns_and_reads_list_them(host_session):
    table = sync_routes(HostTask, now=lambda: NOW, host_columns=COLUMNS)
    route = table[("tasks", None)]
    assert set(COLUMNS) <= set(route.reads) and {"priority", "due_at"} <= set(route.reads)
    route.handler(host_session, Ctx("u1"), Op("dev-1", "put"), {"title": "A", "contact_id": "c1", "extra": "no"})
    task = host_session.get(HostTask, "dev-1")
    assert (task.contact_id, task.loan_id) == ("c1", None)
    route.handler(host_session, Ctx("u1"), Op("dev-1", "patch"), {"loan_id": "l7"})  # only an app column
    host_session.expire_all()
    task = host_session.get(HostTask, "dev-1")
    assert (task.title, task.contact_id, task.loan_id) == ("A", "c1", "l7")
