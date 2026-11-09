from datetime import date, timedelta

import pytest
from conftest import NOW, Base, Task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from bond_tasks_py import TaskCreate, TaskError, TaskUpdate, service

USERS = {"u1", "u2", "u3"}
DAYX = date(2026, 11, 9)


def make(session, owner="u1", **fields):
    data = TaskCreate(**{"title": "Call back", **fields})
    return service.create(session, task_model=Task, owner_user_id=owner, actor_user_id=owner, data=data, now=NOW,
                          user_exists=USERS.__contains__)


def edit(session, task, actor, **fields):
    return service.update(session, task=task, actor_user_id=actor, data=TaskUpdate.model_validate(fields), now=NOW,
                          user_exists=USERS.__contains__)


def code_of(call) -> str:
    with pytest.raises(TaskError) as caught:
        call()
    return caught.value.code


def test_create_sets_owner_creator_and_defaults(session):
    task = make(session, due_date=date(2026, 11, 9))
    assert (task.owner_user_id, task.created_by, task.status, task.mirror_status) == ("u1", "u1", "open", "pending")
    assert task.created_at == NOW and task.id


def test_create_without_a_date_is_not_mirrored(session):
    assert make(session).mirror_status == "skipped"


def test_create_with_mirror_off_is_skipped(session):
    assert make(session, due_date=date(2026, 11, 9), mirror_enabled=False).mirror_status == "skipped"


def test_blank_or_missing_title_is_title_required(session):
    assert code_of(lambda: make(session, title="   ")) == "title_required"
    data = TaskCreate()
    assert code_of(lambda: service.create(session, task_model=Task, owner_user_id="u1", actor_user_id="u1",
                                          data=data, now=NOW)) == "title_required"


def test_due_time_requires_a_date(session):
    err = code_of(lambda: make(session, due_time="09:00"))
    assert err == "due_time_requires_date"


def test_unknown_assignee(session):
    assert code_of(lambda: make(session, assigned_user_id="ghost")) == "unknown_assignee"


def test_replay_by_the_owner_returns_the_existing_row(session):
    first = make(session, id="abc-1", title="One")
    again = make(session, id="abc-1", title="Changed")
    assert again is first and again.title == "One"


def test_another_owners_id_is_taken(session):
    make(session, id="abc-1")
    assert code_of(lambda: make(session, owner="u2", id="abc-1")) == "id_taken"
    assert TaskError("id_taken").status == 409


def test_error_statuses_follow_the_table():
    assert {c: TaskError(c).status for c in (
        "not_task_editor", "not_task_owner", "task_not_found", "unknown_assignee", "title_required",
        "due_time_requires_date", "id_taken")} == {
        "not_task_editor": 403, "not_task_owner": 403, "task_not_found": 404, "unknown_assignee": 422,
        "title_required": 422, "due_time_requires_date": 422, "id_taken": 409}


def test_get_missing_is_task_not_found(session):
    assert code_of(lambda: service.get(session, Task, "nope")) == "task_not_found"


def test_update_omitted_is_unchanged_and_none_clears(session):
    task = make(session, due_date=date(2026, 11, 9), due_time="10:00", notes="n", assigned_user_id="u2")
    edit(session, task, "u1", title="New")
    assert (task.title, task.notes, task.due_time, task.assigned_user_id) == ("New", "n", "10:00", "u2")
    edit(session, task, "u1", notes=None, due_time=None, assigned_user_id=None)
    assert (task.notes, task.due_time, task.assigned_user_id) == (None, None, None)
    assert task.due_date == date(2026, 11, 9)


def test_clearing_the_date_clears_the_time(session):
    task = make(session, due_date=date(2026, 11, 9), due_time="10:00")
    edit(session, task, "u1", due_date=None)
    assert task.due_date is None and task.due_time is None and task.remind_at is None


def test_update_title_cannot_be_blank_or_null(session):
    task = make(session)
    assert code_of(lambda: edit(session, task, "u1", title="")) == "title_required"
    assert code_of(lambda: edit(session, task, "u1", title=None)) == "title_required"


def test_update_due_time_without_date_is_refused(session):
    task = make(session)
    assert code_of(lambda: edit(session, task, "u1", due_time="09:00")) == "due_time_requires_date"


def test_assignee_can_edit_but_a_stranger_cannot(session):
    task = make(session, assigned_user_id="u2")
    edit(session, task, "u2", notes="by assignee")
    assert task.notes == "by assignee"
    assert code_of(lambda: edit(session, task, "u3", notes="x")) == "not_task_editor"


def test_reassign_is_owner_only(session):
    task = make(session, assigned_user_id="u2")
    assert code_of(lambda: edit(session, task, "u2", assigned_user_id="u3")) == "not_task_owner"
    edit(session, task, "u1", assigned_user_id="u3")
    assert task.assigned_user_id == "u3"


def test_a_stranger_reassigning_is_told_not_owner(session):
    task = make(session)
    assert code_of(lambda: edit(session, task, "u3", assigned_user_id="u3")) == "not_task_owner"


def test_resending_the_same_assignee_is_an_edit_not_a_reassign(session):
    task = make(session, assigned_user_id="u2")
    edit(session, task, "u2", assigned_user_id="u2", notes="ok")
    assert task.notes == "ok"


def test_complete_and_reopen(session):
    task = make(session, due_date=date(2026, 11, 9), assigned_user_id="u2")
    service.complete(session, task, "u2", NOW)
    assert (task.status, task.completed_by, task.completed_at, task.mirror_status) == ("done", "u2", NOW, "skipped")
    service.reopen(session, task, "u1", NOW)
    assert (task.status, task.completed_by, task.completed_at, task.mirror_status) == ("open", None, None, "pending")


def test_complete_is_idempotent_and_keeps_first_stamp(session):
    task = make(session)
    service.complete(session, task, "u1", NOW)
    service.complete(session, task, "u1", NOW + timedelta(hours=1))
    assert task.completed_at == NOW


def test_complete_needs_an_editor(session):
    task = make(session)
    assert code_of(lambda: service.complete(session, task, "u3", NOW)) == "not_task_editor"
    assert code_of(lambda: service.reopen(session, task, "u3", NOW)) == "not_task_editor"


def test_cancel_is_owner_only_and_reopen_revives(session):
    task = make(session, assigned_user_id="u2")
    assert code_of(lambda: service.cancel(session, task, "u2", NOW)) == "not_task_owner"
    service.cancel(session, task, "u1", NOW)
    assert task.status == "cancelled"
    assert code_of(lambda: service.reopen(session, task, "u2", NOW)) == "not_task_owner"
    assert code_of(lambda: service.complete(session, task, "u2", NOW)) == "not_task_owner"
    service.reopen(session, task, "u1", NOW)
    assert task.status == "open"


def test_a_cancelled_task_can_be_completed(session):
    task = make(session)
    service.cancel(session, task, "u1", NOW)
    service.complete(session, task, "u1", NOW)
    assert task.status == "done"


def test_delete_is_hard_and_owner_only(session):
    task = make(session, assigned_user_id="u2")
    assert code_of(lambda: service.delete(session, task, "u2")) == "not_task_owner"
    assert service.delete(session, task, "u1") is None
    assert session.get(Task, task.id) is None


def test_delete_returns_the_external_pointer(session):
    task = make(session, due_date=date(2026, 11, 9))
    task.external_event_id, task.external_provider, task.external_account_user_id = "ev-1", "google", "u1"
    pointer = service.delete(session, task, "u1")
    assert (pointer.user_id, pointer.provider, pointer.event_id) == ("u1", "google", "ev-1")


def test_checklist_on_create_and_tick(session):
    task = make(session, checklist=[{"text": "a"}, {"text": "b"}])
    first = task.checklist[0]["id"]
    service.set_checklist_item(task, first, True, NOW, actor_user_id="u1")
    assert task.checklist[0]["done_at"] == "2026-11-08T12:00:00Z" and task.checklist[1]["done_at"] is None
    service.set_checklist_item(task, first, False, NOW)
    assert task.checklist[0]["done_at"] is None


def test_tick_keeps_the_first_done_stamp(session):
    task = make(session, checklist=[{"text": "a"}])
    item = task.checklist[0]["id"]
    service.set_checklist_item(task, item, True, NOW)
    service.set_checklist_item(task, item, True, NOW + timedelta(hours=2))
    assert task.checklist[0]["done_at"] == "2026-11-08T12:00:00Z"


def test_checklist_unknown_item_and_non_editor(session):
    task = make(session, checklist=[{"text": "a"}])
    assert code_of(lambda: service.set_checklist_item(task, "zzz", True, NOW)) == "checklist_item_not_found"
    item = task.checklist[0]["id"]
    assert code_of(lambda: service.set_checklist_item(task, item, True, NOW, actor_user_id="u3")) == "not_task_editor"


def test_checklist_replace_on_update_keeps_ticks_by_id(session):
    task = make(session, checklist=[{"text": "a", "done": True}])
    item = task.checklist[0]["id"]
    edit(session, task, "u1", checklist=[{"id": item, "text": "a"}, {"text": "new"}])
    assert [i["text"] for i in task.checklist] == ["a", "new"] and task.checklist[0]["done_at"]


def test_links_round_trip(session):
    task = make(session, links=[{"kind": "loan", "id": "L1", "label": "Loan one"}])
    assert task.links == [{"kind": "loan", "id": "L1", "label": "Loan one"}]
    edit(session, task, "u1", links=[])
    assert task.links == []


def test_update_marks_mirror_pending_when_a_date_arrives(session):
    task = make(session)
    assert task.mirror_status == "skipped"
    edit(session, task, "u1", due_date=date(2026, 11, 20))
    assert task.mirror_status == "pending"


def test_dropping_the_date_keeps_pending_while_an_event_exists(session):
    task = make(session, due_date=date(2026, 11, 9))
    task.external_event_id = "ev-1"
    edit(session, task, "u1", due_date=None)
    assert task.mirror_status == "pending"  # the mirror pass must delete the event


def test_cancel_clears_completion_and_marks_the_mirror(session):
    task = make(session, due_date=DAYX)
    service.complete(session, task, "u1", NOW)
    assert task.completed_at == NOW and task.mirror_status == "skipped"
    service.cancel(session, task, "u1", NOW)
    assert (task.completed_at, task.completed_by, task.mirror_status) == (None, None, "skipped")
    task.external_event_id = "ev-1"
    service.reopen(session, task, "u1", NOW)
    service.cancel(session, task, "u1", NOW)
    assert task.mirror_status == "pending"  # an event exists: the mirror pass must delete it


def test_a_concurrent_create_with_the_same_id_applies_the_replay_rule(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/race.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    class Blind(Session):
        """The pre-check misses the row (the other writer had not committed yet); the insert then collides."""

        skipped = False

        def get(self, entity, ident, **kw):
            if not self.skipped:
                self.skipped = True
                return None
            return super().get(entity, ident, **kw)

    with factory() as winner:
        make(winner, id="same-id")
        winner.commit()
    for owner, expect in (("u1", None), ("u2", "id_taken")):
        with sessionmaker(bind=engine, expire_on_commit=False, class_=Blind)() as loser:
            call = lambda who=owner: make(loser, owner=who, id="same-id")
            if expect:
                assert code_of(call) == expect
            else:
                assert call().owner_user_id == "u1"


def test_a_non_integrity_error_still_propagates(session):
    make(session, id="dup")
    with pytest.raises(Exception, match="NOT NULL|constraint"):
        service.create(session, task_model=Task, owner_user_id=None, actor_user_id="u1",
                       data=TaskCreate(title="x"), now=NOW)
