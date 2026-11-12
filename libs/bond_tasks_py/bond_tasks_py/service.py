"""Task service functions: ``fn(session, ...)``. They flush, never commit: the caller owns the transaction, so a task
write and its reminder job commit together.

Authorization: an editor is the owner or the assignee. Delete, cancel and reassign are owner-only. Reading is open.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from bond_tasks_py.errors import TaskError
from bond_tasks_py.mirror import mark_mirror, pointer_of
from bond_tasks_py.models import TaskStatus
from bond_tasks_py.protocols import MirrorPointer
from bond_tasks_py.reminders import refresh_remind_at
from bond_tasks_py.schema import TaskCreate, TaskUpdate, checklist_item, normalize_checklist, normalize_links
from bond_tasks_py.timeutil import iso_z, parse_iso, to_naive_utc

UserExists = Callable[[str], bool]


def get(session: Any, task_model: Any, task_id: str) -> Any:
    task = session.get(task_model, task_id)
    if task is None:
        raise TaskError("task_not_found")
    return task


def is_editor(task: Any, user_id: str) -> bool:
    return user_id in (task.owner_user_id, task.assigned_user_id)


def require_editor(task: Any, user_id: str) -> None:
    if not is_editor(task, user_id):
        raise TaskError("not_task_editor")


def require_owner(task: Any, user_id: str) -> None:
    if user_id != task.owner_user_id:
        raise TaskError("not_task_owner")


def _require_for_revival(task: Any, user_id: str) -> None:
    """Editors may complete and reopen; once the owner cancelled a task only the owner may change that."""
    if task.status == TaskStatus.CANCELLED.value:
        require_owner(task, user_id)
    else:
        require_editor(task, user_id)


def _title(value: str | None) -> str:
    title = (value or "").strip()
    if not title:
        raise TaskError("title_required")
    if len(title) > 255:
        raise TaskError("title_required", "A title is at most 255 characters.", 422)
    return title


def _check_assignee(user_id: str | None, user_exists: UserExists | None) -> str | None:
    user_id = user_id or None
    if user_id and user_exists is not None and not user_exists(user_id):
        raise TaskError("unknown_assignee")
    return user_id


def _check_time(task: Any) -> None:
    if task.due_time and not task.due_date:
        raise TaskError("due_time_requires_date")


def create(session: Any, *, task_model: Any, owner_user_id: str, actor_user_id: str, data: TaskCreate, now: datetime,
           tz: str = "UTC", user_exists: UserExists | None = None) -> Any:
    """Insert a task. A client-chosen id replayed by the same owner returns the existing row; another owner's id is
    ``id_taken``."""
    if data.id:
        existing = session.get(task_model, data.id)
        if existing is not None:
            if existing.owner_user_id == owner_user_id:
                return existing
            raise TaskError("id_taken")
    now = to_naive_utc(now)
    task = task_model(
        owner_user_id=owner_user_id, created_by=actor_user_id, title=_title(data.title), notes=data.notes,
        due_date=data.due_date, due_time=data.due_time, priority=data.priority, status=TaskStatus.OPEN.value,
        assigned_user_id=_check_assignee(data.assigned_user_id, user_exists),
        checklist=normalize_checklist(data.checklist, existing=None, now=now), links=normalize_links(data.links),
        remind_minutes_before=data.remind_minutes_before, mirror_enabled=data.mirror_enabled, source=data.source,
        created_at=now, updated_at=now,
    )
    if data.id:
        task.id = data.id
    _check_time(task)
    refresh_remind_at(task, tz)
    mark_mirror(task)
    try:
        with session.begin_nested():
            session.add(task)
            session.flush()
    except IntegrityError:  # a concurrent create with the same id won: apply the replay rule to the winner
        existing = session.get(task_model, data.id) if data.id else None
        if existing is None:
            raise
        if existing.owner_user_id == owner_user_id:
            return existing
        raise TaskError("id_taken") from None
    return task


def update(session: Any, *, task: Any, actor_user_id: str, data: TaskUpdate, now: datetime, tz: str = "UTC",
           user_exists: UserExists | None = None) -> Any:
    """Apply the fields in ``data.model_fields_set``. Omitted = unchanged; ``None`` clears ``due_date`` (and so the
    time), ``due_time``, ``priority``, ``assigned_user_id`` and ``notes``; ``title`` and ``mirror_enabled`` cannot be cleared."""
    sent, now = data.model_fields_set, to_naive_utc(now)
    reassigning = "assigned_user_id" in sent and (data.assigned_user_id or None) != task.assigned_user_id
    if reassigning:
        require_owner(task, actor_user_id)
    else:
        require_editor(task, actor_user_id)
    if "title" in sent:
        task.title = _title(data.title)
    if "notes" in sent:
        task.notes = data.notes
    if "due_date" in sent:
        task.due_date = data.due_date
        if data.due_date is None:
            task.due_time = None
    if "due_time" in sent:
        task.due_time = data.due_time
    if "priority" in sent:
        task.priority = data.priority
    if reassigning:
        task.assigned_user_id = _check_assignee(data.assigned_user_id, user_exists)
    if "checklist" in sent:
        task.checklist = normalize_checklist(data.checklist or [], existing=task.checklist, now=now)
    if "links" in sent:
        task.links = normalize_links(data.links or [])
    if "remind_minutes_before" in sent:
        task.remind_minutes_before = data.remind_minutes_before
    if "mirror_enabled" in sent:
        task.mirror_enabled = data.mirror_enabled
    _check_time(task)
    refresh_remind_at(task, tz)
    mark_mirror(task)
    task.updated_at = now
    session.flush()
    return task


def complete(session: Any, task: Any, actor_user_id: str, now: datetime) -> Any:
    """Idempotent. Open or cancelled becomes done; undoing a cancel is the owner's call."""
    _require_for_revival(task, actor_user_id)
    if task.status != TaskStatus.DONE.value:
        task.status = TaskStatus.DONE.value
        task.completed_at, task.completed_by = to_naive_utc(now), actor_user_id
        task.updated_at = to_naive_utc(now)
        mark_mirror(task)
        session.flush()
    return task


def reopen(session: Any, task: Any, actor_user_id: str, now: datetime) -> Any:
    """Idempotent. Done or cancelled becomes open; undoing a cancel is the owner's call."""
    _require_for_revival(task, actor_user_id)
    if task.status != TaskStatus.OPEN.value:
        task.status = TaskStatus.OPEN.value
        task.completed_at = task.completed_by = None
        task.updated_at = to_naive_utc(now)
        mark_mirror(task)
        session.flush()
    return task


def cancel(session: Any, task: Any, actor_user_id: str, now: datetime) -> Any:
    """Owner only; idempotent."""
    require_owner(task, actor_user_id)
    if task.status != TaskStatus.CANCELLED.value:
        task.status = TaskStatus.CANCELLED.value
        task.completed_at = task.completed_by = None
        task.updated_at = to_naive_utc(now)
        mark_mirror(task)
        session.flush()
    return task


def delete(session: Any, task: Any, actor_user_id: str) -> MirrorPointer | None:
    """Hard delete, owner only. Returns where the external event lives so the caller can remove it after commit."""
    require_owner(task, actor_user_id)
    pointer = pointer_of(task)
    session.delete(task)
    session.flush()
    return pointer


def set_checklist_item(task: Any, item_id: str, done: bool, now: datetime, *, actor_user_id: str | None = None) -> Any:
    """Tick or untick one item. Pass ``actor_user_id`` to enforce the editor rule."""
    if actor_user_id is not None:
        require_editor(task, actor_user_id)
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


__all__ = [
    "cancel", "checklist_item", "complete", "create", "delete", "get", "is_editor", "parse_iso", "reopen",
    "require_editor", "require_owner", "set_checklist_item", "update",
]
