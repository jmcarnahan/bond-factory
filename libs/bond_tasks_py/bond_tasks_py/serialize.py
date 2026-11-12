"""The ``TaskItem`` wire shape (also the shared fixture ``fixtures/tasks/task.json``)."""

from collections.abc import Callable, Mapping
from datetime import date, datetime
from typing import Any

from bond_tasks_py.due import is_overdue
from bond_tasks_py.models import MirrorStatus
from bond_tasks_py.timeutil import iso_z

ITEM_KEYS = (
    "id", "title", "notes", "due_date", "due_time", "priority", "due_at", "status", "owner_user_id", "owner_name",
    "assigned_user_id", "assignee_name", "checklist", "remind_minutes_before", "links",
    "completed_at", "mirror_enabled", "mirror_status", "external_provider", "external_event_id", "source",
    "created_at", "updated_at", "overdue",
)

Names = Callable[[list[str]], dict[str, str]]
Labels = Callable[[list[dict]], Mapping[tuple[str, str], str]]


def _links(task: Any, labels: Mapping[tuple[str, str], str] | None) -> list[dict]:
    out = []
    for entry in task.links or []:
        link = dict(entry)
        if labels and (link.get("kind"), link.get("id")) in labels:
            link["label"] = labels[(link.get("kind"), link.get("id"))]
        out.append(link)
    return out


def task_item(task: Any, *, today: date, now: datetime, names: dict[str, str] | None = None,
              labels: Mapping[tuple[str, str], str] | None = None, extra: Mapping[str, Any] | None = None) -> dict:
    """One task as JSON. ``names`` maps user id to display name (missing = null). ``overdue`` is ``due.is_overdue``
    at ``now``; ``today`` (the viewer's date) only serves a dated task whose ``due_at`` is not yet computed.
    ``labels`` maps ``(kind, id)`` to a current label that replaces the stored one on a matching link.
    ``extra`` adds keys after the 24 above; a key that is one of them is ignored (a base key always wins)."""
    names = names or {}
    item = {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "due_time": task.due_time,
        "priority": task.priority,
        "due_at": iso_z(task.due_at),
        "status": task.status,
        "owner_user_id": task.owner_user_id,
        "owner_name": names.get(task.owner_user_id),
        "assigned_user_id": task.assigned_user_id,
        "assignee_name": names.get(task.assigned_user_id) if task.assigned_user_id else None,
        "checklist": [dict(entry) for entry in (task.checklist or [])],
        "remind_minutes_before": task.remind_minutes_before,
        "links": _links(task, labels),
        "completed_at": iso_z(task.completed_at),
        "mirror_enabled": bool(task.mirror_enabled),
        "mirror_status": task.mirror_status or MirrorStatus.PENDING.value,
        "external_provider": task.external_provider,
        "external_event_id": task.external_event_id,
        "source": task.source or "manual",
        "created_at": iso_z(task.created_at),
        "updated_at": iso_z(task.updated_at),
        "overdue": is_overdue(task, now, viewer_today=today),
    }
    for key, value in (extra or {}).items():
        item.setdefault(key, value)
    return item


def task_items(tasks: list[Any], *, today: date, now: datetime, names: Names | None = None,
               labels: Labels | None = None, extras: Callable[[Any], Mapping[str, Any]] | None = None) -> list[dict]:
    """Many tasks; ``names`` is called once with every owner and assignee id. ``labels`` is called once with every
    link of the page (a list of ``{kind, id, label}`` dicts, none when no task has a link) and returns the current
    label per ``(kind, id)``: it replaces the stored label of a matching link, the others keep theirs.
    ``extras(task)`` returns a mapping merged into that task's item after the base keys (it never overrides one)."""
    ids = sorted({t.owner_user_id for t in tasks} | {t.assigned_user_id for t in tasks if t.assigned_user_id})
    resolved = names(ids) if names is not None and ids else {}
    links = [dict(link) for t in tasks for link in t.links or []]
    current = labels(links) if labels is not None and links else None
    return [task_item(task, today=today, names=resolved, now=now, labels=current,
                      extra=extras(task) if extras is not None else None) for task in tasks]
