"""The "today" view: overdue, today, undated and done today, with counts."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select

from bond_tasks_py.due import local_day_bounds
from bond_tasks_py.models import TaskStatus
from bond_tasks_py.queries import (
    due_today_sql,
    instant_order,
    is_overdue_sql,
    mine,
    viewer_today,
)
from bond_tasks_py.timeutil import to_naive_utc


@dataclass
class TodayResult:
    overdue: list[Any] = field(default_factory=list)
    today: list[Any] = field(default_factory=list)
    undated: list[Any] = field(default_factory=list)
    done_today: list[Any] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {"overdue": 0, "today": 0, "undated": 0, "done_today": 0})


def today(session: Any, *, task_model: Any, user_id: str, now: datetime, viewer_zone: str) -> TodayResult:
    """The user's own tasks (owner or assignee) in four exclusive sections, each ordered by due instant.

    ``overdue``: open and ``due_at < now``. ``today``: open, not overdue, its day (the date of a date-only task,
    else the viewer-zone date of ``due_at``) is the viewer's today or earlier. ``undated``: open without a due date.
    ``done_today``: done with ``completed_at`` inside the viewer's local today. An open task due on a later day
    is in no section."""
    m, now = task_model, to_naive_utc(now)
    day = viewer_today(now, viewer_zone)
    start, end = local_day_bounds(day, viewer_zone)
    open_mine = (mine(m, user_id), m.status == TaskStatus.OPEN.value)
    # the viewer's day: a date-only task by its date, a timed one by the instant (see queries.day_in_range)
    def rows(*where: object) -> list[Any]:
        return list(session.execute(select(m).where(*where).order_by(*instant_order(m))).scalars())

    result = TodayResult(
        overdue=rows(*open_mine, is_overdue_sql(m, now, day)),
        today=rows(*open_mine, due_today_sql(m, now, day, viewer_zone)),
        undated=rows(*open_mine, m.due_date.is_(None)),
        done_today=rows(mine(m, user_id), m.status == TaskStatus.DONE.value, m.completed_at >= start,
                        m.completed_at < end),
    )
    result.counts = {name: len(getattr(result, name)) for name in result.counts}
    return result
