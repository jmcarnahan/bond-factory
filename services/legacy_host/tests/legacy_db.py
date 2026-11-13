"""Build a database the way an app that already exists has it: old tables, old rows, then the adoption migration."""

from sqlalchemy import text

from legacy_host.app import create_app
from legacy_host.db import make_engine
from legacy_host.legacy_ddl import ADOPT, LEGACY_DDL, run

OLD = "2026-11-01 09:00:00"


def old_task(connection, task_id, *, title="Old task", status="open", due_date=None, due_time=None, owner="u-owner",
             assignee=None, sync=1, event_id=None, client=None, case=None) -> None:
    connection.execute(text(
        "INSERT INTO tasks (id, owner_user_id, created_by, assigned_user_id, title, due_date, due_time, status, "
        "sync_to_calendar, calendar_event_id, client_ref, case_ref, created_at, updated_at) VALUES "
        "(:id, :owner, :owner, :assignee, :title, :due_date, :due_time, :status, :sync, :event, :client, :case, "
        f"'{OLD}', '{OLD}')"),
        {"id": task_id, "owner": owner, "assignee": assignee, "title": title, "due_date": due_date,
         "due_time": due_time, "status": status, "sync": sync, "event": event_id, "client": client, "case": case})


def legacy_database(path, fill=None) -> str:
    """Make the old tables at `path`, let `fill(connection)` insert old rows by raw SQL, then adopt. Returns the URL."""
    url = f"sqlite:///{path}"
    engine = make_engine(url)
    run(engine, LEGACY_DDL)
    if fill is not None:
        with engine.begin() as connection:
            fill(connection)
    run(engine, ADOPT)
    engine.dispose()
    return url


def legacy_app(path, fill=None):
    from conftest import TEST_NOW, seed

    app = create_app(legacy_database(path, fill))
    app.state.clock.freeze(TEST_NOW)
    seed(app)
    return app
