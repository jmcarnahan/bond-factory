"""In-memory provider for tests and the fake-mode demo. Same contract as the real providers, no network."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from .errors import CalendarError, EtagMismatch, NotFound
from .models import (
    PATCH_KEYS,
    Attendee,
    CalendarEvent,
    CalendarEventDraft,
    EventPage,
    EventPatch,
    Person,
    attendee_parts,
    merged_attendees,
    to_utc,
)


def _attendee(value: str | Person) -> Attendee:
    name, address = attendee_parts(value)
    return Attendee(name, address, "required", "notResponded")


class FakeCalendarProvider:
    """Events live in ``events`` (assert on it). The etag of an event is ``W/"<n>"`` and ``n`` goes up by one on
    every change, so a stale ``If-Match`` raises ``EtagMismatch`` like the real thing. ``fail_next(exc)`` makes the
    next call raise ``exc`` once (for example ``ReconnectRequired()`` or ``Unavailable()``)."""

    def __init__(self, events: list[CalendarEvent] | None = None, *, organizer_email: str = "me@example.com",
                 id_prefix: str = "fake") -> None:
        """``id_prefix`` makes new ids ``<prefix>-<n>``; give each instance its own so two calendars never share an id."""
        self.id_prefix = id_prefix
        self.events: list[CalendarEvent] = list(events or [])
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._versions: dict[str, int] = {e.id: self._version(e.etag) for e in self.events}
        self._next_id = 1
        self._failure: CalendarError | None = None
        self._organizer = Person("Demo", organizer_email)

    @staticmethod
    def _version(etag: str | None) -> int:
        digits = "".join(c for c in (etag or "") if c.isdigit())
        return int(digits) if digits else 1

    def fail_next(self, exc: CalendarError | None) -> None:
        self._failure = exc

    def _enter(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        failure, self._failure = self._failure, None
        if failure is not None:
            raise failure

    def _find(self, event_id: str) -> CalendarEvent:
        for event in self.events:
            if event.id == event_id:
                return event
        raise NotFound()

    def _stamp(self, event: CalendarEvent) -> None:
        self._versions[event.id] = self._versions.get(event.id, 0) + 1
        event.etag = f'W/"{self._versions[event.id]}"'

    def list_events(self, *, start: datetime, end: datetime, max_events: int = 500,
                    include_cancelled: bool = False) -> EventPage:
        self._enter("list_events", start, end)
        lo, hi = to_utc(start), to_utc(end)
        hits = [e for e in self.events if e.start is not None and e.end is not None
                and e.start < hi and e.end > lo and (include_cancelled or not e.is_cancelled)]
        hits.sort(key=lambda e: e.start)
        return EventPage(events=[replace(e) for e in hits[:max_events]], truncated=len(hits) > max_events)

    def create_event(self, draft: CalendarEventDraft) -> CalendarEvent:
        self._enter("create_event", draft)
        event = CalendarEvent(
            id=f"{self.id_prefix}-{self._next_id}", subject=draft.subject, start=to_utc(draft.start), end=to_utc(draft.end),
            is_all_day=draft.is_all_day, location=draft.location, organizer=self._organizer, is_organizer=True,
            show_as="busy", event_type="singleInstance", preview=(draft.body or "")[:255] or None,
            response_status="organizer", sensitivity="normal", categories=list(draft.categories),
            attendees=[_attendee(a) for a in merged_attendees(draft.attendees)],
            body=draft.body, body_content_type=draft.body_type if draft.body is not None else None,
        )
        self._next_id += 1
        self._stamp(event)
        self.events.append(event)
        return replace(event)

    def update_event(self, event_id: str, patch: EventPatch, *, etag: str | None = None) -> CalendarEvent:
        self._enter("update_event", event_id, dict(patch))
        unknown = set(patch) - set(PATCH_KEYS)
        if unknown:
            raise ValueError(f"unknown patch keys: {sorted(unknown)}")
        if ("start" in patch or "end" in patch) and "is_all_day" not in patch:
            raise ValueError("a patch that changes start or end must also say is_all_day")  # as the Google provider
        event = self._find(event_id)
        if etag is not None and etag != event.etag:
            raise EtagMismatch()
        for key, value in patch.items():
            if key in ("start", "end"):
                value = to_utc(value)
            elif key == "attendees":
                value = [_attendee(a) for a in merged_attendees(value)]
            elif key == "categories":
                value = list(value or [])
            elif key == "body":
                event.body, event.preview = value, (value or "")[:255] or None
                continue
            elif key in ("body_type", "reminder_minutes"):
                if key == "body_type":
                    event.body_content_type = value
                continue
            setattr(event, key, value)
        self._stamp(event)
        return replace(event)

    def delete_event(self, event_id: str) -> None:
        self._enter("delete_event", event_id)
        self.events[:] = [e for e in self.events if e.id != event_id]

    def get_event(self, event_id: str, *, include_body: bool = False) -> CalendarEvent:
        self._enter("get_event", event_id)
        found = replace(self._find(event_id))
        if not include_body:
            found.body = found.body_content_type = None
        return found
