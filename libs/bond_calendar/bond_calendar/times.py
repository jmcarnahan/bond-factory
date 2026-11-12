"""Instant parsing and formatting helpers: everything leaves the lib as aware UTC."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC_NAMES = {"", "UTC", "Etc/UTC", "Z", "tzone://Microsoft/Utc"}

# Windows zone names Graph can echo when a write named a zone (a small, common subset).
WINDOWS_ZONES = {
    "Pacific Standard Time": "America/Los_Angeles",
    "Mountain Standard Time": "America/Denver",
    "Central Standard Time": "America/Chicago",
    "Eastern Standard Time": "America/New_York",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "India Standard Time": "Asia/Kolkata",
    "Tokyo Standard Time": "Asia/Tokyo",
    "AUS Eastern Standard Time": "Australia/Sydney",
}
_FRACTION = re.compile(r"(\.\d+)")


def _zone(name: str | None) -> ZoneInfo | None:
    if name in UTC_NAMES or name is None:
        return None
    try:
        return ZoneInfo(WINDOWS_ZONES.get(name, name))
    except (ZoneInfoNotFoundError, ValueError):
        return None  # unknown zone: read as UTC rather than failing a whole listing


def parse_instant(value: str | None, zone: str | None = None) -> datetime | None:
    """An ISO string as aware UTC. An offset in the string wins; otherwise ``zone`` (IANA or Windows name)
    says where the wall clock is, and no zone means UTC. Unreadable input gives None."""
    if not value or not isinstance(value, str):
        return None
    text = _FRACTION.sub(lambda m: m.group(1)[:7], value.strip()).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        tz = _zone(zone)
        parsed = parsed.replace(tzinfo=tz or UTC)
    return parsed.astimezone(UTC)


def parse_day(value: str | None) -> datetime | None:
    """A ``YYYY-MM-DD`` date as midnight UTC."""
    try:
        return datetime.combine(date.fromisoformat(value or ""), datetime.min.time(), tzinfo=UTC)
    except ValueError:
        return None


def round_to_midnight(value: datetime | None) -> datetime | None:
    """Snap an all-day boundary to the NEAREST midnight UTC (round, not floor): a boundary expressed in UTC from a
    zoned midnight can land at an offset such as 17:00, and rounding recovers the intended date."""
    if value is None:
        return None
    floor = value.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if value.astimezone(UTC) - floor >= timedelta(hours=12):
        floor += timedelta(days=1)
    return floor


def all_day_boundary(value: str | None) -> datetime | None:
    """An all-day boundary from its raw string: the WALL date in the event's own zone becomes midnight UTC.

    The sibling zone name is deliberately ignored: converting a zoned midnight to an instant would move it to the
    previous UTC day east of UTC+12. A wall time that is not midnight (a UTC-expressed boundary) rounds to the
    nearest midnight."""
    if not value or not isinstance(value, str):
        return None
    text = _FRACTION.sub(lambda m: m.group(1)[:7], value.strip()).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return round_to_midnight(parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC))


def iso_z(value: datetime) -> str:
    """``2026-07-25T16:00:00Z`` for a query parameter."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def wall_utc(value: datetime) -> str:
    """Graph's zone-less wall-clock form of a UTC instant (paired with ``timeZone: "UTC"``)."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def windows_name(zone: str) -> str:
    """The Windows zone name Graph expects for a zone. Graph accepts both forms, so a name the lib cannot map
    (a Windows name outside its small table, an IANA name it has no Windows twin for) is passed through unchanged."""
    if zone in WINDOWS_ZONES:
        return zone
    return next((win for win, iana in WINDOWS_ZONES.items() if iana == zone), zone)


def is_utc_zone(zone: object) -> bool:
    return not isinstance(zone, str) or zone in UTC_NAMES


def all_day_dates(start: datetime, end: datetime) -> tuple[date, date]:
    """The start date and the exclusive end date of an all-day draft.

    An all-day draft carries calendar dates at midnight UTC, so a date is the UTC date of ``start`` and of ``end``,
    whatever the provider's zone; the end is never earlier than the day after the start."""
    first = start.astimezone(UTC).date()
    return first, max(end.astimezone(UTC).date(), first + timedelta(days=1))
