"""Naive-UTC helpers. Stored datetimes are naive UTC; the wire carries ISO 8601 with a trailing ``Z``."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    """Aware values convert to UTC and lose the tzinfo; naive values are taken as UTC already."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def iso_z(value: datetime | None) -> str | None:
    return None if value is None else to_naive_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    """An ISO 8601 string (``Z`` or an offset or none) as naive UTC."""
    return to_naive_utc(datetime.fromisoformat(value))


def zone(tz: str | ZoneInfo) -> ZoneInfo:
    return tz if isinstance(tz, ZoneInfo) else ZoneInfo(tz)


def local_to_utc(day: date, clock: time, tz: str | ZoneInfo) -> datetime:
    """A local wall-clock moment as naive UTC."""
    return to_naive_utc(datetime.combine(day, clock, tzinfo=zone(tz)))


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


__all__ = ["iso_z", "local_to_utc", "parse_hhmm", "parse_iso", "timedelta", "to_naive_utc", "utcnow", "zone"]
