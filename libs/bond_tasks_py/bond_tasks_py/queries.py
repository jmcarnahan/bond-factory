"""List and summary queries."""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import String, and_, cast, func, or_, select

from bond_tasks_py.due import local_day_bounds
from bond_tasks_py.models import TaskStatus
from bond_tasks_py.timeutil import to_naive_utc


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


def mine(model: Any, user_id: str):
    return or_(model.owner_user_id == user_id, model.assigned_user_id == user_id)


def viewer_today(now: datetime, viewer_zone: str) -> date:
    """The calendar date of ``now`` (naive UTC) in the viewer's zone."""
    return to_naive_utc(now).replace(tzinfo=UTC).astimezone(ZoneInfo(viewer_zone)).date()


def day_in_range(m: Any, lo: date | None, hi: date | None, viewer_zone: str):
    """The task's DAY for the viewer lies in ``[lo, hi]`` (either end may be open): ``due_date`` for a date-only
    task (or a timed one whose ``due_at`` is not computed yet), else ``due_at`` inside the viewer's local days."""
    by_date = [m.due_date >= lo] if lo is not None else []
    by_date += [m.due_date <= hi] if hi is not None else []
    by_instant = [m.due_at >= local_day_bounds(lo, viewer_zone)[0]] if lo is not None else []
    by_instant += [m.due_at < local_day_bounds(hi, viewer_zone)[1]] if hi is not None else []
    return or_(
        and_(m.due_date.is_not(None), or_(m.due_time.is_(None), m.due_at.is_(None)), *by_date),
        and_(m.due_time.is_not(None), m.due_at.is_not(None), *by_instant),
    )


def is_overdue_sql(m: Any, now: datetime, today: date):
    """SQL form of ``due.is_overdue`` for an open task: ``due_at < now``; not yet computed falls back to the date."""
    return or_(m.due_at < now, and_(m.due_at.is_(None), m.due_date < today))


def not_overdue_sql(m: Any, now: datetime, today: date):
    """The dated open tasks that are not overdue (written positively: SQL negation of a NULL stays NULL)."""
    return or_(m.due_at >= now, and_(m.due_at.is_(None), m.due_date >= today))


def due_today_sql(m: Any, now: datetime, today: date, viewer_zone: str):
    """The TODAY section: not overdue, and its day is the viewer's today or earlier (a date-only task whose date
    has passed for the viewer but whose instant, in the responsible user's zone, is still ahead belongs here)."""
    return and_(day_in_range(m, None, today, viewer_zone), not_overdue_sql(m, now, today))


def instant_order(m: Any) -> tuple:
    """Viewer order: ``due_at`` ascending with NULLs last, newest created first, then id (SQLite and Postgres)."""
    return m.due_at.is_(None), m.due_at, m.created_at.desc(), m.id


def _link_matches(task: Any, kind: str | None, link_id: str) -> bool:
    return any(link.get("id") == link_id and (kind is None or link.get("kind") == kind) for link in task.links or [])


def list_tasks(session: Any, *, task_model: Any, user_id: str, filters: TaskFilters | None = None, limit: int = 25,
               offset: int = 0, link_index_model: Any = None, viewer_zone: str | None = None,
               now: datetime | None = None) -> tuple[list[Any], int]:
    """Soonest due first, undated last. ``scope="all"`` lists everything on a record whoever owns it; the app decides who may ask for it.

    ``link_index_model`` turns the contact filter into an indexed lookup with SQL paging. ``viewer_zone`` orders by
    the due instant and reads date ranges as the viewer's local days (see ``day_in_range``). With ``now`` too, a range that
    holds the viewer's today also holds the not-overdue tasks of earlier days (the TODAY section of ``today``)."""
    f, m = filters or TaskFilters(), task_model
    stmt = select(m)
    if f.scope == "mine":
        stmt = stmt.where(mine(m, user_id))
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
    elif viewer_zone and (f.on_or_before is not None or f.due_from is not None or f.due_to is not None):
        hi = min(d for d in (f.on_or_before, f.due_to) if d is not None) if (f.on_or_before or f.due_to) else None
        window = day_in_range(m, f.due_from, hi, viewer_zone)
        if now is not None:  # a range that holds the viewer's today also holds the not-overdue earlier-day tasks
            day = viewer_today(now, viewer_zone)
            if (f.due_from is None or f.due_from <= day) and (hi is None or hi >= day):
                window = or_(window, due_today_sql(m, to_naive_utc(now), day, viewer_zone))
        stmt = stmt.where(or_(window, m.due_date.is_(None)) if f.include_undated else window)
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
    indexed = bool(f.link_id and link_index_model is not None)
    if indexed:
        ix = link_index_model
        hit = select(ix.task_id).where(ix.ref_id == f.link_id)
        stmt = stmt.where(m.id.in_(hit.where(ix.kind == f.link_kind) if f.link_kind else hit))
    elif f.link_id:
        stmt = stmt.where(cast(m.links, String).contains(json.dumps(f.link_id), autoescape=True))
    if viewer_zone:
        stmt = stmt.order_by(*instant_order(m))
    else:
        stmt = stmt.order_by(m.due_date.is_(None), m.due_date, m.due_time.is_(None), m.due_time,
                             m.created_at.desc(), m.id)
    if f.link_id and not indexed:  # the SQL prefilter is a substring match: finish exactly in Python, then page
        rows = [t for t in session.execute(stmt).scalars() if _link_matches(t, f.link_kind, f.link_id)]
        return rows[offset:offset + limit], len(rows)
    total = session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    return list(session.execute(stmt.offset(offset).limit(limit)).scalars()), total


def summary(session: Any, *, task_model: Any, user_id: str, today: date, now: datetime | None = None,
            viewer_zone: str | None = None) -> dict[str, int]:
    """Badge counts over the user's own (owner or assignee) open tasks.

    With ``now`` and ``viewer_zone``: ``overdue`` is ``due_at < now`` (a dated task with no ``due_at`` yet: its
    date before the viewer's today), ``due_today`` the not-overdue tasks whose day is the viewer's today.
    Otherwise the date-only counts of old, with ``today`` as given."""
    m = task_model
    base = (mine(m, user_id), m.status == TaskStatus.OPEN.value)

    def count(*extra: Any) -> int:
        return session.execute(select(func.count()).select_from(m).where(*base, *extra)).scalar_one()

    if now is not None and viewer_zone:
        now, today = to_naive_utc(now), viewer_today(now, viewer_zone)
        overdue = is_overdue_sql(m, now, today)
        due_today = due_today_sql(m, now, today, viewer_zone)
    else:
        overdue, due_today = m.due_date < today, m.due_date == today
    return {"open": count(), "overdue": count(overdue), "due_today": count(due_today),
            "no_date": count(m.due_date.is_(None))}
