"""The tables as the app had them BEFORE it adopted the modules, as raw DDL, and the migration that adopts them.

`LEGACY_DDL` makes the old tables; `ADOPT` adds only the columns the mixins need and the old table lacks (every one
nullable, no default: the way `ALTER TABLE ... ADD COLUMN` leaves the rows that already exist). Tests build a database
from these, insert old rows by raw SQL, run `ADOPT`, and only then start the host on it.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

LEGACY_DDL = (
    """CREATE TABLE tasks (
        id VARCHAR PRIMARY KEY, owner_user_id VARCHAR NOT NULL, created_by VARCHAR NOT NULL,
        assigned_user_id VARCHAR, title VARCHAR(255) NOT NULL, notes TEXT, due_date DATE, due_time VARCHAR(5),
        status VARCHAR NOT NULL, completed_at DATETIME, completed_by VARCHAR,
        sync_to_calendar BOOLEAN NOT NULL, calendar_event_id VARCHAR, calendar_event_user_id VARCHAR,
        client_ref VARCHAR, case_ref VARCHAR, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""",
    """CREATE TABLE file_share_grants (
        id VARCHAR(36) PRIMARY KEY, token_hash VARCHAR(64) NOT NULL UNIQUE, attachment_id VARCHAR(64) NOT NULL,
        expires_at DATETIME NOT NULL, max_downloads INTEGER, hits INTEGER, revoked_at DATETIME,
        sender_id VARCHAR(64), created_at DATETIME, recipient_note VARCHAR)""",
    """CREATE TABLE user_prefs (
        uid VARCHAR PRIMARY KEY, tz VARCHAR(64), day_start VARCHAR(5), day_end VARCHAR(5), remind_lead INTEGER,
        theme VARCHAR, updated_at DATETIME NOT NULL)""",
)

#: Columns the old tables lack. `purpose` is the only one a row needs a value for; the migration backfills it.
ADOPT = (
    "ALTER TABLE tasks ADD COLUMN priority INTEGER",
    "ALTER TABLE tasks ADD COLUMN due_at DATETIME",
    "ALTER TABLE tasks ADD COLUMN checklist JSON",
    "ALTER TABLE tasks ADD COLUMN links JSON",
    "ALTER TABLE tasks ADD COLUMN remind_minutes_before INTEGER",
    "ALTER TABLE tasks ADD COLUMN mirror_status VARCHAR",
    "ALTER TABLE tasks ADD COLUMN external_provider VARCHAR",
    "ALTER TABLE tasks ADD COLUMN external_etag VARCHAR",
    "ALTER TABLE tasks ADD COLUMN source VARCHAR",
    "ALTER TABLE file_share_grants ADD COLUMN purpose VARCHAR(32) NOT NULL DEFAULT 'share'",
    "ALTER TABLE file_share_grants ADD COLUMN owner_type VARCHAR(64)",
    "ALTER TABLE file_share_grants ADD COLUMN owner_id VARCHAR(64)",
    "ALTER TABLE file_share_grants ADD COLUMN last_downloaded_at DATETIME",
    "ALTER TABLE file_share_grants ADD COLUMN last_ip VARCHAR(200)",
    "ALTER TABLE file_share_grants ADD COLUMN updated_at DATETIME",
)


def run(engine: Engine, statements: tuple[str, ...]) -> None:
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
