"""Who may do what to a task, and the status changes: complete, reopen, cancel, delete, checklist ticks, and a
notice action applied the same way on every path. Service functions flush and never commit.

Authorization goes through a ``Permissions`` (default ``DefaultPermissions``): editing needs ``can_edit``; reassign,
cancel and delete need ``can_own``; complete and reopen need ``can_complete``, except that undoing a cancel needs
``can_own``."""

from datetime import datetime
from typing import Any

from sqlalchemy import delete as sql_delete

from bond_tasks_py.errors import TaskError
from bond_tasks_py.mirror import mark_mirror, pointer_of
from bond_tasks_py.models import TaskStatus
from bond_tasks_py.permissions import DefaultPermissions
from bond_tasks_py.protocols import MirrorPointer, Permissions
from bond_tasks_py.timeutil import iso_z, to_naive_utc

_DEFAULT = DefaultPermissions()


def is_editor(task: Any, user_id: str, permissions: Permissions | None = None) -> bool:
    return (permissions or _DEFAULT).can_edit(task, user_id)


def require_editor(task: Any, user_id: str, permissions: Permissions | None = None) -> None:
    if not (permissions or _DEFAULT).can_edit(task, user_id):
        raise TaskError("not_task_editor")


def require_owner(task: Any, user_id: str, permissions: Permissions | None = None) -> None:
    if not (permissions or _DEFAULT).can_own(task, user_id):
        raise TaskError("not_task_owner")


def _require_for_revival(task: Any, user_id: str, permissions: Permissions | None) -> None:
    """Whoever can complete may complete and reopen; once a task is cancelled only an owner may change that."""
    if task.status == TaskStatus.CANCELLED.value:
        require_owner(task, user_id, permissions)
    elif not (permissions or _DEFAULT).can_complete(task, user_id):
        raise TaskError("not_task_editor")


def complete(session: Any, task: Any, actor_user_id: str, now: datetime, *,
             permissions: Permissions | None = None) -> Any:
    """Idempotent. Open or cancelled becomes done; undoing a cancel is the owner's call."""
    _require_for_revival(task, actor_user_id, permissions)
    if task.status != TaskStatus.DONE.value:
        task.status = TaskStatus.DONE.value
        task.completed_at, task.completed_by = to_naive_utc(now), actor_user_id
        task.updated_at = to_naive_utc(now)
        mark_mirror(task)
        session.flush()
    return task


def reopen(session: Any, task: Any, actor_user_id: str, now: datetime, *,
           permissions: Permissions | None = None) -> Any:
    """Idempotent. Done or cancelled becomes open; undoing a cancel is the owner's call."""
    _require_for_revival(task, actor_user_id, permissions)
    if task.status != TaskStatus.OPEN.value:
        task.status = TaskStatus.OPEN.value
        task.completed_at = task.completed_by = None
        task.updated_at = to_naive_utc(now)
        mark_mirror(task)
        session.flush()
    return task


def cancel(session: Any, task: Any, actor_user_id: str, now: datetime, *,
           permissions: Permissions | None = None) -> Any:
    """Needs ``can_own``; idempotent."""
    require_owner(task, actor_user_id, permissions)
    if task.status != TaskStatus.CANCELLED.value:
        task.status = TaskStatus.CANCELLED.value
        task.completed_at = task.completed_by = None
        task.updated_at = to_naive_utc(now)
        mark_mirror(task)
        session.flush()
    return task


def delete(session: Any, task: Any, actor_user_id: str, *, permissions: Permissions | None = None,
           link_index_model: Any = None) -> MirrorPointer | None:
    """Hard delete, needs ``can_own``. Returns where the external event lives so the caller can remove it after
    commit. With ``link_index_model`` the task's link index rows go in the same flush."""
    require_owner(task, actor_user_id, permissions)
    pointer = pointer_of(task)
    if link_index_model is not None:
        session.execute(sql_delete(link_index_model).where(link_index_model.task_id == task.id))
    session.delete(task)
    session.flush()
    return pointer


def set_checklist_item(task: Any, item_id: str, done: bool, now: datetime, *, actor_user_id: str | None = None,
                       permissions: Permissions | None = None) -> Any:
    """Tick or untick one item. Pass ``actor_user_id`` to enforce the editor rule."""
    if actor_user_id is not None:
        require_editor(task, actor_user_id, permissions)
    items = [dict(entry) for entry in (task.checklist or [])]
    for entry in items:
        if entry["id"] == item_id:
            if done:
                entry["done_at"] = entry.get("done_at") or iso_z(now)
            else:
                entry["done_at"] = None
            task.checklist = items  # a new list: in-place edits of a JSON column are not tracked
            task.updated_at = to_naive_utc(now)
            return task
    raise TaskError("checklist_item_not_found")


def apply_notice_action(session: Any, *, task: Any, action: str, actor_user_id: str, now: datetime,
                        permissions: Permissions | None = None) -> Any:
    """Done completes; cancel cancels (needs ``can_own``); snooze changes nothing (the notice layer re-sends it
    later). Anything else is ``invalid_action``. Returns the task."""
    if action == "done":
        return complete(session, task, actor_user_id, now, permissions=permissions)
    if action == "cancel":
        return cancel(session, task, actor_user_id, now, permissions=permissions)
    if action == "snooze":
        return task
    raise TaskError("invalid_action")
