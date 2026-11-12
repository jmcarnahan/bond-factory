"""Dialect-aware insert for the notice claim: ``INSERT ... ON CONFLICT DO NOTHING`` on PostgreSQL and SQLite."""

from typing import Any

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
