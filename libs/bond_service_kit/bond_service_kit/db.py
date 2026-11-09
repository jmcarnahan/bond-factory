"""Engine and session plumbing, plus the schema contract every lib's mixin tests assert.

Libs ship no migrations. They ship declarative mixins; the app attaches them to its own ``Base`` and migrates. A
``schema_contract`` built from a metadata (the lib's mixin attached to a throwaway ``Base``) is asserted against the app's
engine to prove the app's tables carry the columns the lib needs.
"""

from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _enable_sqlite_fks(dbapi_connection: Any, record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _is_memory_sqlite(url: sa.engine.URL) -> bool:
    return url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:")


def make_session_factory(url: str, *, echo: bool = False, pool_pre_ping: bool = True,
                         **engine_kw: Any) -> tuple[Engine, sessionmaker[Session]]:
    """``(engine, sessionmaker)`` for ``url``.

    SQLite gets foreign keys switched on. An in-memory SQLite URL gets one shared connection (``StaticPool``, usable from
    any thread) so a test's tables are visible to the app under test.
    """
    parsed = sa.make_url(url)
    if _is_memory_sqlite(parsed):
        engine_kw.setdefault("poolclass", StaticPool)
        engine_kw.setdefault("connect_args", {"check_same_thread": False})
    engine = sa.create_engine(url, echo=echo, pool_pre_ping=pool_pre_ping, **engine_kw)
    if parsed.get_backend_name() == "sqlite":
        sa.event.listen(engine, "connect", _enable_sqlite_fks)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: Callable[[], Session]) -> Iterator[Session]:
    """A session for non-request code (scripts, jobs): commits on success, rolls back on error, always closes."""
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(frozen=True)
class SchemaContract:
    """Table name -> column name -> nullable."""

    tables: dict[str, dict[str, bool]] = field(default_factory=dict)

    def problems(self, engine: Engine, *, strict: bool = False) -> list[str]:
        inspector = sa.inspect(engine)
        found: list[str] = []
        existing = set(inspector.get_table_names())
        for table, columns in sorted(self.tables.items()):
            if table not in existing:
                found.append(f"table {table!r} is missing")
                continue
            actual = {c["name"]: bool(c["nullable"]) for c in inspector.get_columns(table)}
            for name, nullable in sorted(columns.items()):
                if name not in actual:
                    found.append(f"{table}.{name} is missing")
                elif actual[name] != nullable:
                    want = "nullable" if nullable else "NOT NULL"
                    found.append(f"{table}.{name} should be {want}")
            if strict:
                found.extend(f"{table}.{name} is not in the contract" for name in sorted(set(actual) - set(columns)))
        return found

    def assert_matches(self, engine: Engine, *, strict: bool = False) -> None:
        """Raise ``AssertionError`` listing every difference. Extra columns the app added are fine unless ``strict``."""
        found = self.problems(engine, strict=strict)
        if found:
            raise AssertionError("schema does not match the contract:\n  " + "\n  ".join(found))


def schema_contract(metadata: sa.MetaData, *, tables: Iterable[str] | None = None) -> SchemaContract:
    """The contract for ``metadata`` (optionally only the named ``tables``)."""
    wanted = set(tables) if tables is not None else None
    return SchemaContract({
        t.name: {c.name: bool(c.nullable) for c in t.columns}
        for t in metadata.sorted_tables if wanted is None or t.name in wanted
    })
