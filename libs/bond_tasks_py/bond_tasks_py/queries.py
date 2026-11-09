"""List and summary queries."""

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import String, and_, cast, func, or_, select

from bond_tasks_py.models import TaskStatus


@dataclass(frozen=True)
class TaskFilters:
    """The route query. ``scope="mine"`` = owner or assignee; ``status`` open|done|all (``all`` includes cancelled)."""

    scope: str = "mine"
    status: str = "open"
    on_or_before: date | None = None
    due_from: date | None = None
    due_to: date | None = None
    include_undated: bool = False
    no_date: bool = False
    owner_user_id: str | None = None
    assigned_user_id: str | None = None
    assigned_to_me: bool = False
    link_kind: str | None = None  # narrows link_id; ignored alone
    link_id: str | None = None


def _mine(model: Any, user_id: str):
    return or_(model.owner_user_id == user_id, model.assigned_user_id == user_id)


def _link_matches(task: Any, kind: str | None, link_id: str) -> bool:
    return any(link.get("id") == link_id and (kind is None or link.get("kind") == kind) for link in task.links or [])


def list_tasks(session: Any, *, task_model: Any, user_id: str, filters: TaskFilters | None = None, limit: int = 25,
               offset: int = 0) -> tuple[list[Any], int]:
    """Soonest due first, undated last. ``scope="all"`` lists everything on a record whoever owns it; the app decides who may ask for it."""
    f, m = filters or TaskFilters(), task_model
    stmt = select(m)
    if f.scope == "mine":
        stmt = stmt.where(_mine(m, user_id))
    if f.status in (TaskStatus.OPEN.value, TaskStatus.DONE.value):
        stmt = stmt.where(m.status == f.status)
    if f.owner_user_id:
        stmt = stmt.where(m.owner_user_id == f.owner_user_id)
    if f.assigned_user_id:
        stmt = stmt.where(m.assigned_user_id == f.assigned_user_id)
    if f.assigned_to_me:
        stmt = stmt.where(m.assigned_user_id == user_id)
    if f.no_date:
        stmt = stmt.where(m.due_date.is_(None))
    else:
        bounds = []
        if f.on_or_before is not None:
            bounds.append(m.due_date <= f.on_or_before)
        if f.due_from is not None:
            bounds.append(m.due_date >= f.due_from)
        if f.due_to is not None:
            bounds.append(m.due_date <= f.due_to)
        if bounds:
            window = and_(*bounds)
            stmt = stmt.where(or_(window, m.due_date.is_(None)) if f.include_undated else window)
    if f.link_id:
        stmt = stmt.where(cast(m.links, String).contains(json.dumps(f.link_id), autoescape=True))
    stmt = stmt.order_by(m.due_date.is_(None), m.due_date, m.due_time.is_(None), m.due_time, m.created_at.desc(), m.id)
    if f.link_id:  # the SQL prefilter is a substring match: finish exactly in Python, then page
        rows = [t for t in session.execute(stmt).scalars() if _link_matches(t, f.link_kind, f.link_id)]
        return rows[offset:offset + limit], len(rows)
    total = session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    return list(session.execute(stmt.offset(offset).limit(limit)).scalars()), total


def summary(session: Any, *, task_model: Any, user_id: str, today: date) -> dict[str, int]:
    """Badge counts over the user's own (owner or assignee) open tasks."""
    m = task_model
    base = (_mine(m, user_id), m.status == TaskStatus.OPEN.value)

    def count(*extra: Any) -> int:
        return session.execute(select(func.count()).select_from(m).where(*base, *extra)).scalar_one()

    return {
        "open": count(),
        "overdue": count(m.due_date < today),
        "due_today": count(m.due_date == today),
        "no_date": count(m.due_date.is_(None)),
    }
