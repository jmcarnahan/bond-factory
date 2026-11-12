"""Naive-UTC helper. Datetimes are stored naive UTC; the wire is ISO 8601 with a trailing Z."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
