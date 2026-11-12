"""The "today" view: overdue, today, undated and done today, with counts."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TodayResult:
    overdue: list[Any] = field(default_factory=list)
    today: list[Any] = field(default_factory=list)
    undated: list[Any] = field(default_factory=list)
    done_today: list[Any] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: {"overdue": 0, "today": 0, "undated": 0, "done_today": 0})


def today(session: Any, *, task_model: Any, user_id: str, now: datetime, viewer_zone: str,
          link_index_model: Any = None) -> TodayResult:
    """The user's tasks in the four sections, exclusive."""
    raise NotImplementedError("today.today is not implemented yet")
