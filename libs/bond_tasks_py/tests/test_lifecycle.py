from datetime import date

import pytest
from conftest import NOW, Task
from support_core import Anyone

from bond_tasks_py import TaskCreate, TaskError, service
from bond_tasks_py.errors import CODES
from bond_tasks_py.lifecycle import apply_notice_action


def make(session, **kw):
    return service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="T", due_date=date(2026, 3, 12), **kw), now=NOW)


def act(session, task, action, actor="u1", **kw):
    return apply_notice_action(session, task=task, action=action, actor_user_id=actor, now=NOW, **kw)


def test_done_completes_for_whoever_can_complete(session):
    task = make(session, assigned_user_id="u2")
    assert act(session, task, "done", "u2") is task and task.status == "done" and task.completed_by == "u2"


def test_cancel_needs_can_own(session):
    task = make(session, assigned_user_id="u2")
    with pytest.raises(TaskError) as caught:
        act(session, task, "cancel", "u2")
    assert caught.value.code == "not_task_owner" and task.status == "open"
    assert act(session, task, "cancel", "u1").status == "cancelled"


def test_snooze_changes_nothing(session):
    task = make(session)
    before = (task.status, task.updated_at, task.due_at)
    assert act(session, task, "snooze") is task
    assert (task.status, task.updated_at, task.due_at) == before


def test_an_unknown_action_is_invalid_action_422(session):
    task = make(session)
    with pytest.raises(TaskError) as caught:
        act(session, task, "explode")
    assert (caught.value.code, caught.value.status) == ("invalid_action", 422) and "invalid_action" in CODES


def test_the_policy_is_passed_through(session):
    task = make(session)
    assert act(session, task, "done", "u3", permissions=Anyone()).status == "done"


@pytest.mark.parametrize("closed", ["done", "cancelled"])
@pytest.mark.parametrize("action", ["done", "cancel"])
def test_a_stale_done_or_cancel_on_a_closed_task_changes_nothing(session, closed, action):
    task = make(session)
    task.status = closed
    before = (task.status, task.updated_at, task.completed_at)
    assert act(session, task, action) is task
    assert (task.status, task.updated_at, task.completed_at) == before
