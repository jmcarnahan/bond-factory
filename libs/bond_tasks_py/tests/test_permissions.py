"""Permissions seam: every service function asks the policy, errors keep their codes."""

from datetime import date

import pytest
from conftest import NOW, Task
from support_core import Admin, Anyone, CoOfficer

from bond_tasks_py import TaskCreate, TaskError, TaskUpdate, service
from bond_tasks_py.lifecycle import set_checklist_item

USERS = {"u1", "u2", "u3", "u9"}


def make(session, **kw):
    return service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                          data=TaskCreate(title="T", due_date=date(2026, 3, 12), **kw), now=NOW,
                          user_exists=USERS.__contains__)


def code_of(call) -> str:
    with pytest.raises(TaskError) as caught:
        call()
    return caught.value.code


def update(session, task, actor, permissions=None, **fields):
    return service.update(session, task=task, actor_user_id=actor, data=TaskUpdate.model_validate(fields), now=NOW,
                          user_exists=USERS.__contains__, permissions=permissions)


def test_default_policy_refuses_a_third_user_everywhere(session):
    task = make(session)
    assert code_of(lambda: update(session, task, "u3", title="x")) == "not_task_editor"
    assert code_of(lambda: service.complete(session, task, "u3", NOW)) == "not_task_editor"
    assert code_of(lambda: service.cancel(session, task, "u3", NOW)) == "not_task_owner"
    assert code_of(lambda: service.delete(session, task, "u3")) == "not_task_owner"
    assert code_of(lambda: set_checklist_item(task, "i", True, NOW, actor_user_id="u3")) == "not_task_editor"


def test_a_co_officer_policy_lets_a_third_user_edit_and_complete_but_not_own(session):
    task = make(session)
    policy = CoOfficer()
    assert update(session, task, "u3", policy, title="Edited").title == "Edited"
    assert service.complete(session, task, "u3", NOW, permissions=policy).status == "done"
    assert service.reopen(session, task, "u3", NOW, permissions=policy).status == "open"
    assert code_of(lambda: update(session, task, "u3", policy, assigned_user_id="u2")) == "not_task_owner"
    assert code_of(lambda: service.cancel(session, task, "u3", NOW, permissions=policy)) == "not_task_owner"
    assert code_of(lambda: service.delete(session, task, "u3", permissions=policy)) == "not_task_owner"


def test_an_admin_policy_may_own_everything(session):
    task = make(session)
    policy = Admin()
    assert update(session, task, "u9", policy, assigned_user_id="u2").assigned_user_id == "u2"
    assert service.cancel(session, task, "u9", NOW, permissions=policy).status == "cancelled"
    assert service.reopen(session, task, "u9", NOW, permissions=policy).status == "open"
    service.delete(session, task, "u9", permissions=policy)
    assert session.get(Task, task.id) is None


def test_anyone_may_complete_but_still_not_edit(session):
    task = make(session)
    policy = Anyone()
    assert service.complete(session, task, "u3", NOW, permissions=policy).completed_by == "u3"
    assert service.reopen(session, task, "u3", NOW, permissions=policy).status == "open"
    assert code_of(lambda: update(session, task, "u3", policy, title="x")) == "not_task_editor"


def test_undoing_a_cancel_needs_can_own_not_can_complete(session):
    task = make(session)
    service.cancel(session, task, "u1", NOW)
    assert code_of(lambda: service.complete(session, task, "u3", NOW, permissions=Anyone())) == "not_task_owner"
    assert code_of(lambda: service.reopen(session, task, "u3", NOW, permissions=Anyone())) == "not_task_owner"
    assert service.reopen(session, task, "u1", NOW, permissions=Anyone()).status == "open"


def test_the_checklist_tick_uses_can_edit(session):
    task = make(session, checklist=[{"id": "i", "text": "a"}])
    set_checklist_item(task, "i", True, NOW, actor_user_id="u3", permissions=CoOfficer())
    assert task.checklist[0]["done_at"]
