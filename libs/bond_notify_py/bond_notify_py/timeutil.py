"""Naive-UTC helpers. Datetimes are stored naive UTC; the wire is ISO 8601 with a trailing Z."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    """An aware datetime converted to UTC and made naive; a naive one is taken to be UTC already."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def iso_z(value: datetime | None) -> str | None:
    """Naive UTC (or aware, converted) to ``2030-01-01T12:00:00Z``; None stays None."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(microsecond=0).isoformat() + "Z"
