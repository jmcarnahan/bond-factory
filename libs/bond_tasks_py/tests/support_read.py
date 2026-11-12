"""Shared test support for the today view, link index and settings tests. Loaded by conftest as a pytest plugin;
the helpers are imported by name (``from support_read import mk``)."""
import json
from datetime import date, datetime
from pathlib import Path

from bond_tasks_py.link_index import reindex_links
from bond_tasks_py.timeutil import parse_iso

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "tasks"
FIXTURE_NOW = datetime(2026, 3, 11, 20, 0)  # the instant of today.json and summary.json
FIXTURE_ZONE = "America/Los_Angeles"
CREATED = datetime(2026, 3, 1, 12, 0)


def mk(session, task_model, id, *, owner="u1", due=None, due_time=None, due_at=None, status="open",
       completed_at=None, assigned=None, links=(), created_at=CREATED, index_model=None, **extra):
    """Insert a task straight into the table (the services are tested elsewhere) and flush."""
    task = task_model(id=id, owner_user_id=owner, created_by=owner, assigned_user_id=assigned, title=id,
                      due_date=due, due_time=due_time, due_at=due_at, status=status, completed_at=completed_at,
                      links=[dict(link) for link in links], created_at=created_at, updated_at=created_at, **extra)
    session.add(task)
    session.flush()
    if index_model is not None:
        reindex_links(session, index_model, task)
    return task


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def load_today_fixture(session, task_model) -> None:
    """The tasks of fixtures/tasks/today.json as rows (all four sections)."""
    for section in ("overdue", "today", "undated", "done_today"):
        for item in load_fixture("today.json")[section]:
            mk(session, task_model, item["id"], owner=item["owner_user_id"], status=item["status"],
               due=date.fromisoformat(item["due_date"]) if item["due_date"] else None, due_time=item["due_time"],
               due_at=parse_iso(item["due_at"]) if item["due_at"] else None,
               completed_at=parse_iso(item["completed_at"]) if item["completed_at"] else None,
               priority=item["priority"], created_at=parse_iso(item["created_at"]))
