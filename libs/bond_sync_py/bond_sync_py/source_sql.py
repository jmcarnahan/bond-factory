"""Render the idempotent psql script that makes a Postgres database a sync source: the replication role, its SELECT-only
grants, the publication and the WAL cap. The app commits the result and a test keeps it equal to this render."""

from __future__ import annotations

import re
from collections.abc import Sequence

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def render_source_sql(
    tables: Sequence[str],
    publication: str = "powersync",
    role: str = "powersync",
    *,
    app_name: str = "app",
    script_path: str = "sync/sql/01_source.sql",
    generated_by: str = "",
    wal_keep: str = "2GB",
) -> str:
    """The script for ``tables``. Names are validated, so nothing here can be SQL injection even from a careless table list."""
    for name in (*tables, publication, role):
        if not _NAME.match(name):
            raise ValueError(f"bad SQL name {name!r}")
    if not tables or len(set(tables)) != len(tables):
        raise ValueError("tables must be a non-empty list without duplicates")
    if not re.fullmatch(r"[0-9A-Za-z]{1,16}", wal_keep):
        raise ValueError(f"bad WAL size {wal_keep!r}")
    listing = ", ".join(tables)
    regen = f" Regenerate with: {generated_by}" if generated_by else ""
    header = [
        f"-- GENERATED FILE. Do not edit by hand.{regen}",
        "-- A test fails when this file differs from the render of the synced-table list.",
        "--",
        f"-- Sync source setup for {app_name}. Idempotent; run it as the role that owns the app's tables, AFTER the",
        "-- migrations (the tables must exist), against the app database:",
        f"--   psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 -v ps_password='<password for the {role} role>' -f {script_path}",
        "-- ps_password is REQUIRED (the script stops without it; there is no default).",
        f"-- The {role} role gets SELECT on the synced tables ONLY (no default privileges): a table added later is granted by",
        "-- bond_sync_py.publication.add_table in the migration that creates it.",
        "-- Needs wal_level=logical (a restart on a managed Postgres).",
        "-- Never FOR ALL TABLES: tables that are not synced stay unpublished.",
        "",
    ]
    # The only interpolated values are validated names and the WAL size, never request data.
    body = f"""\\set ON_ERROR_STOP on
\\if :{{?ps_password}}
\\else
  \\echo '{script_path}: pass -v ps_password=<password for the {role} role>; there is no default.'
  DO $$ BEGIN RAISE EXCEPTION 'ps_password is required'; END $$;
  \\quit
\\endif
SELECT (:'ps_password' = '') AS ps_password_empty \\gset
\\if :ps_password_empty
  \\echo '{script_path}: ps_password must not be empty.'
  DO $$ BEGIN RAISE EXCEPTION 'ps_password is empty'; END $$;
  \\quit
\\endif
\\set synced_tables '{listing}'

-- the replication role
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') AS role_missing \\gset
\\if :role_missing
  CREATE ROLE {role} WITH REPLICATION BYPASSRLS LOGIN PASSWORD :'ps_password';
\\endif
ALTER ROLE {role} WITH REPLICATION BYPASSRLS LOGIN PASSWORD :'ps_password';

-- read access to the synced tables only; anything granted earlier is withdrawn
GRANT USAGE ON SCHEMA public TO {role};
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role};
GRANT SELECT ON :synced_tables TO {role};

-- the publication: exactly the synced tables
SELECT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = '{publication}') AS publication_exists \\gset
\\if :publication_exists
  ALTER PUBLICATION {publication} SET TABLE :synced_tables;
\\else
  CREATE PUBLICATION {publication} FOR TABLE :synced_tables;
\\endif

-- bound the WAL a stalled slot can pin (superuser only; on a managed Postgres run ALTER SYSTEM as the superuser)
SELECT rolsuper AS is_super FROM pg_roles WHERE rolname = current_user \\gset
\\if :is_super
  ALTER SYSTEM SET max_slot_wal_keep_size = '{wal_keep}';
  SELECT pg_reload_conf() AS reloaded \\gset
\\endif
"""  # nosec B608
    return "\n".join(header) + "\n" + body
