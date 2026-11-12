"""Calendar provider clients for Google and Microsoft: one normalised event, typed errors, no storage."""

from .errors import (
    CalendarError,
    EtagMismatch,
    Forbidden,
    InvalidAttendee,
    NotFound,
    ReconnectRequired,
    Unavailable,
)
from .fake import FakeCalendarProvider
from .google import GoogleCalendarProvider
from .graph import MsGraphCalendarProvider
from .models import (
    PATCH_KEYS,
    Attendee,
    CalendarEvent,
    CalendarEventDraft,
    EventPage,
    EventPatch,
    Person,
    to_utc,
)
from .protocol import CalendarProvider

__version__ = "0.1.0"

__all__ = [
    "PATCH_KEYS",
    "Attendee",
    "CalendarError",
    "CalendarEvent",
    "CalendarEventDraft",
    "CalendarProvider",
    "EtagMismatch",
    "EventPage",
    "EventPatch",
    "FakeCalendarProvider",
    "Forbidden",
    "GoogleCalendarProvider",
    "InvalidAttendee",
    "MsGraphCalendarProvider",
    "NotFound",
    "Person",
    "ReconnectRequired",
    "Unavailable",
    "to_utc",
]
