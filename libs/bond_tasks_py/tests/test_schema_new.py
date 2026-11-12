"""The four new tables, pinned literally (columns, keys, indexes), as ``test_schema`` pins ``tasks``."""

from conftest import Ledger, LinkIndex, Outbox, UserSettings
from sqlalchemy import UniqueConstraint, inspect

from bond_tasks_py import (
    TASK_LINK_INDEX_COLUMNS,
    TASK_NOTICE_LEDGER_COLUMNS,
    TASK_NOTICE_OUTBOX_COLUMNS,
    TASK_USER_SETTINGS_COLUMNS,
)


def indexes(model) -> dict[str, list[str]]:
    return {ix.name: [c.name for c in ix.columns] for ix in model.__table__.indexes}


def test_user_settings_table():
    table = UserSettings.__table__
    assert table.name == "task_user_settings"
    assert list(table.c.keys()) == ["user_id", "time_zone", "start_of_day", "end_of_day", "lead_minutes",
                                    "updated_at"]
    assert {c.name: c.nullable for c in table.c} == TASK_USER_SETTINGS_COLUMNS
    assert [c.name for c in table.primary_key] == ["user_id"] and not table.foreign_keys
    assert table.c.time_zone.type.length == 64 and table.c.start_of_day.type.length == 5
    assert all(table.c[n].default is None and table.c[n].nullable for n in ("start_of_day", "end_of_day", "lead_minutes"))


def test_user_settings_nothing_is_stored_on_insert(session):
    row = UserSettings(user_id="u1")
    session.add(row)
    session.flush()
    assert (row.time_zone, row.start_of_day, row.end_of_day, row.lead_minutes) == (None, None, None, None)
    assert row.updated_at is not None


def test_link_index_table():
    table = LinkIndex.__table__
    assert table.name == "task_link_index"
    assert list(table.c.keys()) == ["task_id", "kind", "ref_id"]
    assert {c.name: c.nullable for c in table.c} == TASK_LINK_INDEX_COLUMNS
    assert [c.name for c in table.primary_key] == ["task_id", "kind", "ref_id"]
    assert indexes(LinkIndex) == {"ix_task_link_ref": ["kind", "ref_id", "task_id"]}
    assert table.c.kind.type.length == 32 and table.c.ref_id.type.length == 128


def test_ledger_table():
    table = Ledger.__table__
    assert table.name == "task_notice_ledger"
    assert list(table.c.keys()) == ["id", "task_id", "user_id", "stage", "seq", "deadline_token", "status",
                                    "stage_at", "payload", "claimed_at"]
    assert {c.name: c.nullable for c in table.c} == TASK_NOTICE_LEDGER_COLUMNS
    assert not any(TASK_NOTICE_LEDGER_COLUMNS.values()), "no ledger column is nullable"
    assert [c.name for c in table.primary_key] == ["id"] and table.c.id.type.length == 32
    assert (table.c.stage.type.length, table.c.status.type.length, table.c.deadline_token.type.length) == (8, 8, 32)
    unique = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert [[col.name for col in c.columns] for c in unique] == [
        ["task_id", "user_id", "stage", "seq", "deadline_token"]]
    assert indexes(Ledger) == {"ix_task_notice_ledger_task_id": ["task_id"],
                               "ix_task_notice_ledger_claimed_at": ["claimed_at"]}


def test_outbox_table():
    table = Outbox.__table__
    assert table.name == "task_notice_outbox"
    assert list(table.c.keys()) == ["ledger_id", "channel", "delivered_at", "failed_at", "attempts", "last_error",
                                    "lease_until", "created_at"]
    assert {c.name: c.nullable for c in table.c} == TASK_NOTICE_OUTBOX_COLUMNS
    assert [c.name for c in table.primary_key] == ["ledger_id", "channel"]
    assert indexes(Outbox) == {"ix_task_notice_outbox_pending": ["failed_at", "delivered_at", "lease_until"]}
    assert table.c.attempts.default.arg == 0


def test_all_tables_are_created_together(factory):
    names = set(inspect(factory.kw["bind"]).get_table_names())
    assert {"tasks", "task_user_settings", "task_link_index", "task_notice_ledger", "task_notice_outbox"} <= names
