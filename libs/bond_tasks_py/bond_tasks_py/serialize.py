"""The ``TaskItem`` wire shape (also the shared fixture ``fixtures/tasks/task.json``)."""

from collections.abc import Callable
from datetime import date
from typing import Any

from bond_tasks_py.models import MirrorStatus, TaskStatus
from bond_tasks_py.timeutil import iso_z

ITEM_KEYS = (
    "id", "title", "notes", "due_date", "due_time", "status", "owner_user_id", "owner_name", "assigned_user_id",
    "assignee_name", "checklist", "remind_minutes_before", "remind_at", "reminded_at", "links", "completed_at",
    "mirror_enabled", "mirror_status", "external_provider", "external_event_id", "source", "created_at", "updated_at",
    "overdue",
)

Names = Callable[[list[str]], dict[str, str]]


def is_overdue(task: Any, today: date) -> bool:
    return bool(task.status == TaskStatus.OPEN.value and task.due_date and task.due_date < today)


def task_item(task: Any, *, today: date, names: dict[str, str] | None = None) -> dict:
    """One task as JSON. ``names`` maps user id to display name (missing = null). ``overdue`` is measured against
    the client's ``today``."""
    names = names or {}
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "due_time": task.due_time,
        "status": task.status,
        "owner_user_id": task.owner_user_id,
        "owner_name": names.get(task.owner_user_id),
        "assigned_user_id": task.assigned_user_id,
        "assignee_name": names.get(task.assigned_user_id) if task.assigned_user_id else None,
        "checklist": [dict(entry) for entry in (task.checklist or [])],
        "remind_minutes_before": task.remind_minutes_before,
        "remind_at": iso_z(task.remind_at),
        "reminded_at": iso_z(task.reminded_at),
        "links": [dict(entry) for entry in (task.links or [])],
        "completed_at": iso_z(task.completed_at),
        "mirror_enabled": bool(task.mirror_enabled),
        "mirror_status": task.mirror_status or MirrorStatus.PENDING.value,
        "external_provider": task.external_provider,
        "external_event_id": task.external_event_id,
        "source": task.source or "manual",
        "created_at": iso_z(task.created_at),
        "updated_at": iso_z(task.updated_at),
        "overdue": is_overdue(task, today),
    }


def task_items(tasks: list[Any], *, today: date, names: Names | None = None) -> list[dict]:
    """Many tasks; ``names`` is called once with every owner and assignee id."""
    ids = sorted({t.owner_user_id for t in tasks} | {t.assigned_user_id for t in tasks if t.assigned_user_id})
    resolved = names(ids) if names is not None and ids else {}
    return [task_item(task, today=today, names=resolved) for task in tasks]
