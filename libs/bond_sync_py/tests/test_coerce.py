from datetime import datetime

import pytest
import sqlalchemy as sa

from bond_sync_py import coerce, has_nul
from bond_sync_py.coerce import _to_bool

META = sa.MetaData()
T = sa.Table(
    "t", META,
    sa.Column("id", sa.String), sa.Column("n", sa.Integer), sa.Column("x", sa.Float), sa.Column("b", sa.Boolean),
    sa.Column("at", sa.DateTime), sa.Column("text", sa.Text),
)
TABLES = {"t": T}


@pytest.mark.parametrize("raw,expected", [(1, True), (0, False), ("1", True), ("false", False), ("TRUE", True), (True, True)])
def test_bool_forms(raw, expected):
    assert coerce(TABLES, "t", {"b": raw})["b"] is expected


@pytest.mark.parametrize("raw", ["yes", 2, 0.5, [1]])
def test_bool_rejects(raw):
    with pytest.raises(ValueError):
        _to_bool(raw)


def test_numbers_text_and_none():
    out = coerce(TABLES, "t", {"n": " 7 ", "x": "2.5", "text": "hi", "id": None})
    assert out == {"n": 7, "x": 2.5, "text": "hi", "id": None}
    assert coerce(TABLES, "t", {"n": 3.0})["n"] == 3


@pytest.mark.parametrize("data", [{"n": True}, {"n": 1.5}, {"n": "x"}, {"x": "nan"}, {"x": "inf"}, {"x": False}, {"text": 5}])
def test_bad_numbers_and_text(data):
    with pytest.raises(ValueError):
        coerce(TABLES, "t", data)


def test_datetime_iso_with_z():
    out = coerce(TABLES, "t", {"at": "2026-11-08T17:04:05.123Z"})["at"]
    assert out == datetime(2026, 11, 8, 17, 4, 5, 123000)  # naive UTC for a naive column
    with pytest.raises(ValueError):
        coerce(TABLES, "t", {"at": "yesterday"})


def test_client_only_columns_pass_through_and_json_by_name():
    out = coerce(TABLES, "t", {"other_user_id": "u2", "j": '{"a": [1]}', "flag": 1}, client_bools={"flag"}, client_json={"j"})
    assert out == {"other_user_id": "u2", "j": {"a": [1]}, "flag": True}


def test_only_limits_what_is_read():
    assert coerce(TABLES, "t", {"n": "abc", "text": "ok"}, ("text",)) == {"text": "ok"}


def test_unknown_table_passes_through():
    assert coerce(TABLES, "other", {"a": 1}) == {"a": 1}


def test_has_nul_nested():
    assert has_nul("a\x00") and has_nul({"k": ["x", {"y\x00": 1}]}) and has_nul({"a\x00": 1})
    assert not has_nul({"a": ["b", 1, None]})


def test_aware_datetime_for_naive_column_is_converted_to_utc():
    out = coerce(TABLES, "t", {"at": "2026-01-01T10:00:00+02:00"})["at"]
    assert out == datetime(2026, 1, 1, 8, 0) and out.tzinfo is None
    assert coerce(TABLES, "t", {"at": "2026-01-01T10:00:00Z"})["at"] == datetime(2026, 1, 1, 10, 0)
    assert coerce(TABLES, "t", {"at": "2026-01-01T10:00:00"})["at"] == datetime(2026, 1, 1, 10, 0)


def test_aware_column_keeps_its_offset():
    aware = sa.Table("a", META, sa.Column("at", sa.DateTime(timezone=True)))
    out = coerce({"a": aware}, "a", {"at": "2026-01-01T10:00:00+02:00"})["at"]
    assert out.utcoffset().total_seconds() == 7200
