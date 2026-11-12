"""Pins the ``push_devices`` table: apps migrate it by hand, so a silent change here is a breaking change."""

from conftest import PushDevice
from sqlalchemy import DateTime, String, UniqueConstraint

from bond_push_py import PUSH_DEVICE_COLUMNS

EXPECTED = {
    "id": (String, None),
    "user_id": (String, None),
    "device_id": (String, 64),
    "token": (String, 255),
    "platform": (String, 8),
    "environment": (String, 12),
    "topic": (String, 255),
    "last_seen_at": (DateTime, None),
    "disabled_at": (DateTime, None),
    "created_at": (DateTime, None),
}


def test_table_name_and_columns():
    table = PushDevice.__table__
    assert table.name == "push_devices"
    assert set(table.c.keys()) == set(EXPECTED) == set(PUSH_DEVICE_COLUMNS)
    for name, (type_class, length) in EXPECTED.items():
        column = table.c[name]
        assert type(column.type) is type_class, name
        assert getattr(column.type, "length", None) == length, name
        assert column.nullable is PUSH_DEVICE_COLUMNS[name], name


def test_keys_and_uniqueness():
    table = PushDevice.__table__
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert table.c.token.unique is True
    assert table.c.user_id.index is True
    assert "ix_push_devices_user_id" in {i.name for i in table.indexes}
    unique = [c for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert ["user_id", "device_id"] in [[col.name for col in c.columns] for c in unique]
