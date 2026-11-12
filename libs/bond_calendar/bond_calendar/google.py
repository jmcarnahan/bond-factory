"""Google Calendar client (the signed-in user's primary calendar). Needs the ``calendar.events`` scope to write."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx

from .errors import CalendarError, NotFound
from .models import (
    PATCH_KEYS,
    CalendarEvent,
    CalendarEventDraft,
    EventPage,
    EventPatch,
    attendee_parts,
    merged_attendees,
    to_utc,
)
from .normalize import google_body, google_event, google_is_dropped
from .times import all_day_dates, iso_z
from .transport import call, json_body

LOGGER = logging.getLogger("bond_calendar.google")
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
FIELDS = ("id,etag,summary,status,start,end,location,htmlLink,description,organizer,attendees,hangoutLink,"
          "conferenceData,transparency,visibility,recurringEventId")
LIST_FIELDS = f"nextPageToken,items({FIELDS})"
PAGE_SIZE = 250
MAX_PAGES = 25


def _time(value: datetime, all_day: bool) -> dict[str, str]:
    value = to_utc(value)
    return {"date": value.date().isoformat()} if all_day else {"dateTime": iso_z(value), "timeZone": "UTC"}


def _attendee(value: Any) -> dict[str, str]:
    name, address = attendee_parts(value)
    return {"email": address} if not name else {"email": address, "displayName": name}


def wire_fields(values: dict[str, Any], *, all_day: bool | None = None) -> dict[str, Any]:
    """Draft or patch keys (only those present) as a Google event body. Google has no categories: they are dropped."""
    flag = bool(values.get("is_all_day")) if all_day is None else all_day
    out: dict[str, Any] = {}
    if "subject" in values:
        out["summary"] = values["subject"]
    if flag and values.get("start") is not None and values.get("end") is not None:
        first, last = all_day_dates(to_utc(values["start"]), to_utc(values["end"]))
        out["start"], out["end"] = {"date": first.isoformat()}, {"date": last.isoformat()}
    else:
        if values.get("start") is not None:
            out["start"] = _time(values["start"], flag)
        if values.get("end") is not None:
            out["end"] = _time(values["end"], flag)
    if "location" in values:
        out["location"] = values["location"] or ""
    if "body" in values:
        out["description"] = values["body"] or ""
    if "attendees" in values:
        out["attendees"] = [_attendee(a) for a in merged_attendees(values["attendees"])]
    if "reminder_minutes" in values:  # present and None clears the reminder
        minutes = values["reminder_minutes"]
        out["reminders"] = {"useDefault": False, "overrides": (
            [] if minutes is None else [{"method": "popup", "minutes": int(minutes)}])}
    elif values.get("reminder_off"):  # create only: no calendar default reminder, no overrides
        out["reminders"] = {"useDefault": False}
    return out


def _draft_fields(draft: CalendarEventDraft) -> dict[str, Any]:
    """A new event never says anything about reminders unless the draft asks for one (minutes or off)."""
    return {k: v for k, v in vars(draft).items()
            if not (k == "reminder_minutes" and v is None) and not (k == "reminder_off" and not v)}


class GoogleCalendarProvider:
    def __init__(self, token: Callable[[], str], http: httpx.Client, *,
                 refresh: Callable[[], str] | None = None) -> None:
        self._token, self._http, self._refresh = token, http, refresh

    def _call(self, method: str, url: str, **kw: Any) -> httpx.Response:
        return call(self._http, self._token, method, url, refresh=self._refresh, **kw)

    def list_events(self, *, start: datetime, end: datetime, max_events: int = 500,
                    include_cancelled: bool = False) -> EventPage:
        params: dict[str, Any] = {
            "timeMin": iso_z(to_utc(start)), "timeMax": iso_z(to_utc(end)), "singleEvents": "true",
            "orderBy": "startTime", "maxResults": min(PAGE_SIZE, max(1, max_events)), "fields": LIST_FIELDS,
        }
        if include_cancelled:
            params["showDeleted"] = "true"
        page = EventPage()
        for _ in range(MAX_PAGES):
            data = json_body(self._call("GET", EVENTS_URL, params=params))
            for raw in data.get("items") or []:
                if not isinstance(raw, dict) or (google_is_dropped(raw) and not (
                        include_cancelled and raw.get("status") == "cancelled")):
                    continue
                if len(page.events) >= max_events:
                    page.truncated = True
                    return page
                page.events.append(google_event(raw))
            token = data.get("nextPageToken")
            if not token:
                return page
            params["pageToken"] = token
        page.truncated = True
        LOGGER.warning("events paged %s times without finishing; returning %s events", MAX_PAGES, len(page.events))
        return page

    def create_event(self, draft: CalendarEventDraft) -> CalendarEvent:
        data = json_body(self._call("POST", EVENTS_URL, json=wire_fields(_draft_fields(draft))))
        if not data.get("id"):  # not NotFound: a mirror would read that as "gone" and create a duplicate
            raise CalendarError(502, "invalid_response", "The calendar returned no event.")
        return google_event(data)

    def update_event(self, event_id: str, patch: EventPatch, *, etag: str | None = None) -> CalendarEvent:
        unknown = set(patch) - set(PATCH_KEYS)
        if unknown:
            raise ValueError(f"unknown patch keys: {sorted(unknown)}")
        if ("start" in patch or "end" in patch) and "is_all_day" not in patch:
            raise ValueError("a patch that changes start or end must also say is_all_day")
        headers = {"If-Match": etag} if etag else {}
        data = json_body(self._call("PATCH", f"{EVENTS_URL}/{event_id}", json=wire_fields(patch),
                                    headers=headers))
        return google_event(data) if data.get("id") else self.get_event(event_id)

    def delete_event(self, event_id: str) -> None:
        try:
            self._call("DELETE", f"{EVENTS_URL}/{event_id}")
        except NotFound:
            return

    def get_event(self, event_id: str, *, include_body: bool = False) -> CalendarEvent:
        raw = json_body(self._call("GET", f"{EVENTS_URL}/{event_id}", params={"fields": FIELDS}))
        event = google_event(raw)
        return google_body(event, raw) if include_body else event
