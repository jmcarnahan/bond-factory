"""Migration helper: a new synced table must join the publication in the migration that creates it."""

from __future__ import annotations

import re

import sqlalchemy as sa

DEFAULT_PUBLICATION = "powersync"
DEFAULT_ROLE = "powersync"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def add_table(op, name: str, *, publication: str = DEFAULT_PUBLICATION, role: str = DEFAULT_ROLE) -> bool:
    """``ALTER PUBLICATION <publication> ADD TABLE <name>`` and ``GRANT SELECT`` on it to ``role`` (when that role exists),
    on Postgres only and only when the publication exists (the source script creates it after the first migration, so a
    fresh database or SQLite has none). ``op`` is the alembic ``op``. Returns True when it ran."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    for ident in (name, publication, role):
        if not _NAME.match(ident):
            raise ValueError(f"bad SQL name {ident!r}")
    if bind.execute(sa.text("SELECT 1 FROM pg_publication WHERE pubname = :n"), {"n": publication}).first() is None:
        return False
    already = bind.execute(
        sa.text("SELECT 1 FROM pg_publication_tables WHERE pubname = :n AND schemaname = current_schema() AND tablename = :t"),
        {"n": publication, "t": name},
    ).first()
    if already is not None:
        return False
    op.execute(f'ALTER PUBLICATION {publication} ADD TABLE "{name}"')
    # the role reads only the synced tables (the source script grants no default privileges), so the new one is granted here
    if bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).first() is not None:
        op.execute(f'GRANT SELECT ON "{name}" TO {role}')
    return True
