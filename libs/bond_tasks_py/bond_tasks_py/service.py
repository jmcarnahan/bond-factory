"""Task service functions: ``fn(session, ...)``. They flush, never commit: the caller owns the transaction, so a task
write and its notices commit together.

Authorization: an editor is the owner or the assignee. Delete, cancel and reassign are owner-only. Reading is open.
"""

from collections.abc import Callable, Collection, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from bond_tasks_py.due import compute_due_at, valid_zone
from bond_tasks_py.errors import TaskError
from bond_tasks_py.hostcols import apply_extras
from bond_tasks_py.lifecycle import (
    cancel,
    complete,
    delete,
    is_editor,
    reopen,
    require_editor,
    require_owner,
    set_checklist_item,
)
from bond_tasks_py.mirror import mark_mirror
from bond_tasks_py.models import TaskStatus
from bond_tasks_py.protocols import AfterWrite, Permissions, UserPrefs
from bond_tasks_py.schema import TaskCreate, TaskUpdate, checklist_item, normalize_checklist, normalize_links
from bond_tasks_py.timeutil import parse_iso, to_naive_utc

UserExists = Callable[[str], bool]


def get(session: Any, task_model: Any, task_id: str) -> Any:
    task = session.get(task_model, task_id)
    if task is None:
        raise TaskError("task_not_found")
    return task


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


def _sent_zone(data: TaskCreate | TaskUpdate) -> str | None:
    """The zone sent with a write (None when none was sent); an unknown name is ``invalid_time_zone``."""
    name = data.time_zone
    if name is None:
        return None
    if not valid_zone(name):
        raise TaskError("invalid_time_zone")
    return name


def _write_zone(data: TaskCreate | TaskUpdate, writer_zone: str | None, prefs: Any, session: Any,
                actor_user_id: str) -> str | None:
    """The zone of a write: the zone sent, else ``writer_zone``, else the actor's stored zone from ``prefs`` (empty
    means not stored). None falls through to the app default."""
    sent = _sent_zone(data)
    if sent:
        return sent
    if writer_zone:
        return writer_zone
    if prefs is not None:
        return prefs.for_user(session, actor_user_id).time_zone or None
    return None


def _due_at(task: Any, data: TaskCreate | TaskUpdate, *, zone: str | None, actor_user_id: str, tz: str,
            session: Any, prefs: Any) -> datetime | None:
    """The task's due instant under rules 3 and 4 of the due-instant decision. ``zone`` is the zone of this write
    (sent, else the writer's stored zone); a date-only task uses it only when the writer is the responsible user."""
    responsible = task.assigned_user_id or task.owner_user_id
    if task.due_time:
        return compute_due_at(task.due_date, task.due_time, writer_zone=zone, responsible_prefs=UserPrefs(),
                              app_tz=tz, client_due_at=data.due_at, sent_zone=data.time_zone)
    found = prefs.for_user(session, responsible) if prefs is not None else UserPrefs()
    return compute_due_at(task.due_date, None, writer_zone=zone if actor_user_id == responsible else None,
                          responsible_prefs=found, app_tz=tz)


def create(session: Any, *, task_model: Any, owner_user_id: str, actor_user_id: str, data: TaskCreate, now: datetime,
           tz: str = "UTC", user_exists: UserExists | None = None, writer_zone: str | None = None,
           prefs: Any = None, extras: Mapping[str, Any] | None = None,
           host_columns: Collection[str] = (), after_write: AfterWrite | None = None) -> Any:
    """Insert a task. A client-chosen id replayed by the same owner returns the existing row; another owner's id is
    ``id_taken``. ``writer_zone`` is the writer's stored zone (when None and ``prefs`` is given, the actor's stored zone is read from
    ``prefs``), ``prefs`` a ``Preferences`` (None: defaults for
    everyone), ``extras`` app columns named in ``host_columns``, ``after_write(session, task)`` runs after the flush."""
    if data.id:
        existing = session.get(task_model, data.id)
        if existing is not None:
            if existing.owner_user_id == owner_user_id:
                return existing
            raise TaskError("id_taken")
    now = to_naive_utc(now)
    zone = _write_zone(data, writer_zone, prefs, session, actor_user_id)
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
    apply_extras(task, extras, host_columns)
    task.due_at = _due_at(task, data, zone=zone, actor_user_id=actor_user_id, tz=tz, session=session, prefs=prefs)
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
    if after_write is not None:
        after_write(session, task)
    return task


def update(session: Any, *, task: Any, actor_user_id: str, data: TaskUpdate, now: datetime, tz: str = "UTC",
           user_exists: UserExists | None = None, writer_zone: str | None = None, prefs: Any = None,
           permissions: Permissions | None = None, extras: Mapping[str, Any] | None = None,
           host_columns: Collection[str] = (), after_write: AfterWrite | None = None) -> Any:
    """Apply the fields in ``data.model_fields_set``. Omitted = unchanged; ``None`` clears ``due_date`` (and so the
    time and ``due_at``), ``due_time``, ``priority``, ``assigned_user_id`` and ``notes``; ``title`` and
    ``mirror_enabled`` cannot be cleared. ``due_at`` is recomputed only when the date, the time or the assignee
    actually differs from what is stored (a timed task is not recomputed by a reassignment)."""
    sent, now = data.model_fields_set, to_naive_utc(now)
    zone = _write_zone(data, writer_zone, prefs, session, actor_user_id)
    reassigning = "assigned_user_id" in sent and (data.assigned_user_id or None) != task.assigned_user_id
    if reassigning:
        require_owner(task, actor_user_id, permissions)
    else:
        require_editor(task, actor_user_id, permissions)
    before = (task.due_date, task.due_time)
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
    apply_extras(task, extras, host_columns)
    if task.due_date is None:
        task.due_at = None
    elif before != (task.due_date, task.due_time) or (reassigning and not task.due_time):
        task.due_at = _due_at(task, data, zone=zone, actor_user_id=actor_user_id, tz=tz, session=session,
                              prefs=prefs)
    mark_mirror(task)
    task.updated_at = now
    session.flush()
    if after_write is not None:
        after_write(session, task)
    return task


__all__ = [
    "cancel", "checklist_item", "complete", "create", "delete", "get", "is_editor", "parse_iso", "reopen",
    "require_editor", "require_owner", "set_checklist_item", "update",
]
