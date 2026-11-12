"""Naive-UTC helpers. Datetimes are stored naive UTC; the wire is ISO 8601 with a trailing Z."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(moment: datetime) -> datetime:
    """An aware datetime converted to UTC and made naive; a naive one is taken as already UTC."""
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)
