"""Pins the ``notices`` table: apps migrate it by hand, so a silent change here is a breaking change."""

from conftest import Notice
from sqlalchemy import JSON, DateTime, String, Text

from bond_notify_py import NOTICE_COLUMNS

EXPECTED = {
    "id": (String, 32),
    "user_id": (String, None),
    "kind": (String, 32),
    "title": (String, 255),
    "body": (Text, None),
    "data": (JSON, None),
    "source_id": (String, None),
    "created_at": (DateTime, None),
    "read_at": (DateTime, None),
    "dismissed_at": (DateTime, None),
}


def test_table_name_and_columns():
    table = Notice.__table__
    assert table.name == "notices"
    assert set(table.c.keys()) == set(EXPECTED) == set(NOTICE_COLUMNS)
    for name, (type_class, length) in EXPECTED.items():
        column = table.c[name]
        assert type(column.type) is type_class, name
        assert getattr(column.type, "length", None) == length, name
        assert column.nullable is NOTICE_COLUMNS[name], name


def test_primary_key_and_indexes():
    table = Notice.__table__
    assert [c.name for c in table.primary_key.columns] == ["id"]
    indexes = {i.name: [c.name for c in i.columns] for i in table.indexes}
    assert indexes["ix_notices_user_created"] == ["user_id", "created_at"]
    assert table.c.source_id.index is True
