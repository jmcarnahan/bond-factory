"""Normalised calendar values. Every instant is a timezone-aware UTC datetime; all-day boundaries sit at midnight UTC.

The lib stores nothing: the calendar stays the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

#: The keys an ``EventPatch`` may carry (same names as ``CalendarEventDraft``). Absent keys are left alone.
PATCH_KEYS = (
    "subject", "start", "end", "is_all_day", "location", "body", "body_type", "categories", "attendees",
    "reminder_minutes",
)

#: A dict of only the changed keys, named like the draft fields.
EventPatch = dict[str, Any]


@dataclass(frozen=True)
class Person:
    name: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class Attendee:
    name: str | None = None
    email: str | None = None
    type: str | None = None  # required | optional | resource
    response: str | None = None  # accepted | declined | tentativelyAccepted | notResponded | ...


@dataclass
class CalendarEvent:
    id: str
    etag: str | None = None
    subject: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    is_all_day: bool = False
    location: str | None = None
    organizer: Person | None = None
    attendees: list[Attendee] = field(default_factory=list)
    is_organizer: bool = False
    is_online_meeting: bool = False
    join_url: str | None = None
    show_as: str | None = None  # free | tentative | busy | oof | workingElsewhere | unknown
    is_cancelled: bool = False
    series_master_id: str | None = None
    event_type: str | None = None  # singleInstance | occurrence | exception | seriesMaster
    preview: str | None = None
    web_link: str | None = None
    response_status: str | None = None
    sensitivity: str | None = None  # normal | personal | private | confidential
    categories: list[str] = field(default_factory=list)
    body: str | None = None  # only from get_event(include_body=True)
    body_content_type: str | None = None  # "html" | "text", with body


@dataclass
class CalendarEventDraft:
    subject: str
    start: datetime
    end: datetime
    is_all_day: bool = False
    location: str | None = None
    body: str | None = None
    body_type: str = "text"  # "text" | "html"
    categories: list[str] = field(default_factory=list)
    attendees: list[str] = field(default_factory=list)  # e-mail addresses
    reminder_minutes: int | None = None
    #: Create only. True switches the reminder off on a new event instead of leaving the mailbox default.
    #: Ignored when ``reminder_minutes`` is set. Not a patch key: to clear a reminder later, patch
    #: ``reminder_minutes`` to None.
    reminder_off: bool = False


@dataclass
class EventPage:
    events: list[CalendarEvent] = field(default_factory=list)
    truncated: bool = False


def to_utc(value: datetime) -> datetime:
    """Aware UTC; a naive datetime is taken as already UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
