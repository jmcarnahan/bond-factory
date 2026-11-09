"""The calendar provider contract. Providers take a ``token`` callable and an ``httpx.Client``; nothing else."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from .models import CalendarEvent, CalendarEventDraft, EventPage, EventPatch


@runtime_checkable
class CalendarProvider(Protocol):
    def list_events(self, *, start: datetime, end: datetime, max_events: int = 500,
                    include_cancelled: bool = False) -> EventPage:
        """Events overlapping [start, end), recurrences expanded, ordered by start."""

    def create_event(self, draft: CalendarEventDraft) -> CalendarEvent: ...

    def update_event(self, event_id: str, patch: EventPatch, *, etag: str | None = None) -> CalendarEvent:
        """Send only the changed keys. With ``etag`` a concurrent edit raises ``EtagMismatch``.

        A patch that changes ``start`` or ``end`` must also carry ``is_all_day`` (Google raises ``ValueError``
        otherwise). ``reminder_minutes: None`` clears the reminder."""

    def delete_event(self, event_id: str) -> None:
        """Idempotent: an event that is already gone (204, 404 or 410) is not an error."""

    def get_event(self, event_id: str, *, include_body: bool = False) -> CalendarEvent: ...
