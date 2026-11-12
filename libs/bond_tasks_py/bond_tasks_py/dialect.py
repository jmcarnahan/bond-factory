"""Dialect-aware insert for the notice claim: ``INSERT ... ON CONFLICT DO NOTHING`` on PostgreSQL and SQLite."""

import weakref
from typing import Any

from sqlalchemy import event
from sqlalchemy.dialects import postgresql, sqlite


def dialect_insert(session: Any, table: Any) -> Any:
    """The dialect's ``insert`` for ``table`` (it has ``on_conflict_do_nothing``). Needs no driver import; any other
    dialect raises ``NotImplementedError``."""
    name = session.get_bind().dialect.name
    if name == "postgresql":
        return postgresql.insert(table)
    if name == "sqlite":
        return sqlite.insert(table)
    raise NotImplementedError(f"no ON CONFLICT insert for dialect {name!r}")


_PREPARED: "weakref.WeakSet[Any]" = weakref.WeakSet()


def sqlite_savepoint_setup(engine: Any) -> Any:
    """Make SAVEPOINT behave on SQLite with the default driver: without this a released savepoint commits the outer
    transaction, so a sweep would commit. This is the setup the SQLAlchemy documentation prescribes
    (``isolation_level=None`` on connect, an explicit BEGIN on begin). Call it once per engine, BEFORE its first
    connection is made (the connect listener only reaches connections opened afterwards); returns the engine.
    ``sweep_due`` and ``deliver_pending`` refuse a SQLite session that was not prepared. PostgreSQL needs nothing."""

    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    _PREPARED.add(engine)
    return engine


def ensure_savepoint_safe(session: Any) -> None:
    """Raise RuntimeError when ``session`` runs on a SQLite engine that was not prepared with
    ``sqlite_savepoint_setup`` (an engine set up by hand passes when its DBAPI connection has
    ``isolation_level`` None). Other dialects pass. The failure it prevents is silent: a released savepoint
    commits the caller's transaction, so a rollback would not undo the sweep."""
    bind = session.get_bind()
    engine = getattr(bind, "engine", bind)
    if engine.dialect.name != "sqlite" or engine in _PREPARED:
        return
    raw = session.connection().connection.dbapi_connection
    if getattr(raw, "isolation_level", "") is None:
        return
    raise RuntimeError(
        "this SQLite engine is not prepared for savepoints: with the default driver settings a released savepoint "
        "commits the outer transaction. Call bond_tasks_py.dialect.sqlite_savepoint_setup(engine) once, before the "
        "engine's first connection (or set isolation_level=None and emit BEGIN on the begin event yourself).")
