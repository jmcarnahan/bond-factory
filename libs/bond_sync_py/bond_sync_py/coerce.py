"""A device's SQLite values as the server's types: 0/1 to bool, numeric text to numbers, JSON text to dict or list."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

import sqlalchemy as sa


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("0", "1", "true", "false"):
        return value.strip().lower() in ("1", "true")
    raise ValueError("not a boolean")


def _to_int(value):
    if isinstance(value, bool):
        raise ValueError("not a whole number")  # noqa: TRY004
    if isinstance(value, str):
        return int(value.strip())
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("not a whole number")
        return int(value)
    return value


def _to_float(value):
    if isinstance(value, bool):
        raise ValueError("not a number")  # noqa: TRY004
    number = float(value.strip()) if isinstance(value, str) else float(value)
    if not math.isfinite(number):
        raise ValueError("not a finite number")
    return number


def _to_json(value):
    return json.loads(value) if isinstance(value, str) else value


def _to_datetime(value, aware: bool):
    """ISO text to a datetime (a trailing Z is UTC); datetimes pass through. For a timezone-naive column an aware value is
    converted to UTC and loses its tzinfo, so no offset is silently dropped by the driver."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.strip())
    elif not isinstance(value, datetime):
        raise ValueError("not a timestamp")  # noqa: TRY004
    if not aware and value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


def coerce(
    tables: Mapping[str, sa.Table],
    table: str,
    data: dict,
    only: Iterable[str] | None = None,
    *,
    client_bools: Iterable[str] = frozenset(),
    client_json: Iterable[str] = frozenset(),
) -> dict:
    """Convert ``data`` for ``table``. With ``only`` just those keys are read, so a malformed column nobody uses never rejects
    an op. Columns the table lacks (client-only columns) pass through, except names in ``client_bools`` / ``client_json``.
    Raises ``ValueError`` on a value of the wrong shape. JSON conversion is by name, never by column type."""
    if only is not None and only != ():
        data = {k: data[k] for k in only if k in data}
    meta = tables.get(table)
    bools, jsons = set(client_bools), set(client_json)
    out: dict = {}
    for key, value in data.items():
        column = meta.columns.get(key) if meta is not None else None
        if value is None:
            out[key] = None
        elif key in bools:
            out[key] = _to_bool(value)
        elif key in jsons:
            out[key] = _to_json(value)
        elif column is None:
            out[key] = value
        elif isinstance(column.type, sa.Boolean):
            out[key] = _to_bool(value)
        elif isinstance(column.type, sa.Integer):
            out[key] = _to_int(value)
        elif isinstance(column.type, sa.Float):
            out[key] = _to_float(value)
        elif isinstance(column.type, sa.DateTime):
            out[key] = _to_datetime(value, bool(column.type.timezone))
        elif isinstance(column.type, sa.String):  # Text is a String subclass
            if not isinstance(value, str):
                raise ValueError("not text")
            out[key] = value
        else:
            out[key] = value
    return out


def has_nul(value) -> bool:
    """True when any string inside ``value`` (nested dicts and lists included) holds a NUL byte, which Postgres refuses."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(has_nul(k) or has_nul(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(has_nul(v) for v in value)
    return False
