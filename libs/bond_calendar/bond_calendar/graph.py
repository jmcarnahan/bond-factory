"""Microsoft Graph calendar client (the signed-in user's default calendar, ``/me``)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime
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
from .normalize import graph_body, graph_event
from .times import all_day_dates, is_utc_zone, iso_z, wall_utc, windows_name
from .transport import call, json_body

LOGGER = logging.getLogger("bond_calendar.graph")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
VIEW_SELECT = (
    "id,subject,start,end,isAllDay,location,attendees,organizer,isOnlineMeeting,onlineMeeting,showAs,"
    "isCancelled,seriesMasterId,type,bodyPreview,webLink,responseStatus,sensitivity,categories,isOrganizer"
)
PAGE_SIZE = 100
MAX_PAGES = 25  # only so a nextLink that never advances cannot spin forever


def _instant(value: datetime) -> dict[str, str]:
    return {"dateTime": wall_utc(to_utc(value)), "timeZone": "UTC"}


def _local_day(value: date, zone: str) -> dict[str, str]:
    return {"dateTime": f"{value.isoformat()}T00:00:00", "timeZone": windows_name(zone)}


def _attendee(value: Any) -> dict[str, Any]:
    name, address = attendee_parts(value)
    mail = {"address": address} if not name else {"address": address, "name": name}
    return {"emailAddress": mail, "type": "required"}


def wire_fields(values: dict[str, Any], zone: str | None = None) -> dict[str, Any]:
    """Draft or patch keys (only those present) as a Graph event body.

    With a non-UTC ``zone`` an all-day event is written as local midnight of its date in that zone."""
    out: dict[str, Any] = {}
    if "subject" in values:
        out["subject"] = values["subject"]
    local_days = (values.get("is_all_day") and zone
                  and values.get("start") is not None and values.get("end") is not None)
    if local_days and not isinstance(zone, str):
        raise CalendarError(400, "invalid_timezone", "The calendar time zone must be a zone name string.")
    if local_days and not is_utc_zone(zone):
        first, last = all_day_dates(to_utc(values["start"]), to_utc(values["end"]))
        out["start"], out["end"] = _local_day(first, zone), _local_day(last, zone)
    else:
        if values.get("start") is not None:
            out["start"] = _instant(values["start"])
        if values.get("end") is not None:
            out["end"] = _instant(values["end"])
    if "is_all_day" in values:
        out["isAllDay"] = bool(values["is_all_day"])
    if "location" in values:
        out["location"] = {"displayName": values["location"] or ""}
    if "body" in values:
        out["body"] = {"contentType": "html" if values.get("body_type") == "html" else "text",
                       "content": values["body"] or ""}
    if "categories" in values:
        out["categories"] = list(values["categories"] or [])
    if "attendees" in values:
        out["attendees"] = [_attendee(a) for a in merged_attendees(values["attendees"])]
    if "reminder_minutes" in values:  # present and None clears the reminder
        if values["reminder_minutes"] is None:
            out["isReminderOn"] = False
        else:
            out["isReminderOn"] = True
            out["reminderMinutesBeforeStart"] = int(values["reminder_minutes"])
    elif values.get("reminder_off"):  # create only: no mailbox default reminder
        out["isReminderOn"] = False
    return out


def _draft_fields(draft: CalendarEventDraft) -> dict[str, Any]:
    """A new event never says anything about reminders unless the draft asks for one (minutes or off)."""
    return {k: v for k, v in vars(draft).items()
            if not (k == "reminder_minutes" and v is None) and not (k == "reminder_off" and not v)}


class MsGraphCalendarProvider:
    def __init__(self, token: Callable[[], str], http: httpx.Client, *, timezone: str = "UTC",
                 refresh: Callable[[], str] | None = None) -> None:
        self._token, self._http, self._refresh, self._zone = token, http, refresh, timezone
        self._prefer = {"Prefer": f'outlook.timezone="{timezone}"'}

    def _call(self, method: str, url: str, **kw: Any) -> httpx.Response:
        return call(self._http, self._token, method, url, headers=dict(self._prefer, **kw.pop("headers", {})),
                    refresh=self._refresh, **kw)

    def list_events(self, *, start: datetime, end: datetime, max_events: int = 500,
                    include_cancelled: bool = False) -> EventPage:
        url: str = f"{GRAPH_BASE}/me/calendarView"
        params: dict[str, Any] | None = {
            "startDateTime": iso_z(to_utc(start)), "endDateTime": iso_z(to_utc(end)), "$select": VIEW_SELECT,
            "$orderby": "start/dateTime", "$top": PAGE_SIZE,
        }
        page = EventPage()
        for _ in range(MAX_PAGES):
            data = json_body(self._call("GET", url, params=params))
            for raw in data.get("value") or []:
                if not isinstance(raw, dict):
                    continue
                event = graph_event(raw)
                if event.is_cancelled and not include_cancelled:
                    continue
                if len(page.events) >= max_events:
                    page.truncated = True
                    return page
                page.events.append(event)
            url, params = data.get("@odata.nextLink"), None  # the link already carries its query
            if not url:
                return page
        page.truncated = True
        LOGGER.warning("calendarView paged %s times without finishing; returning %s events", MAX_PAGES,
                       len(page.events))
        return page

    def create_event(self, draft: CalendarEventDraft) -> CalendarEvent:
        data = json_body(self._call("POST", f"{GRAPH_BASE}/me/events", json=wire_fields(_draft_fields(draft), self._zone)))
        if not data.get("id"):  # not NotFound: a mirror would read that as "gone" and create a duplicate
            raise CalendarError(502, "invalid_response", "The calendar returned no event.")
        return graph_event(data)

    def update_event(self, event_id: str, patch: EventPatch, *, etag: str | None = None) -> CalendarEvent:
        unknown = set(patch) - set(PATCH_KEYS)
        if unknown:
            raise ValueError(f"unknown patch keys: {sorted(unknown)}")
        if ("start" in patch or "end" in patch) and "is_all_day" not in patch:
            raise ValueError("a patch that changes start or end must also say is_all_day")
        headers = {"If-Match": etag} if etag else {}
        data = json_body(self._call("PATCH", f"{GRAPH_BASE}/me/events/{event_id}", json=wire_fields(patch, self._zone),
                                    headers=headers))
        # An empty answer is still a successful patch: read the event back instead of reporting a failure.
        return graph_event(data) if data.get("id") else self.get_event(event_id)

    def delete_event(self, event_id: str) -> None:
        try:
            self._call("DELETE", f"{GRAPH_BASE}/me/events/{event_id}")
        except NotFound:
            return  # already gone (404 or 410)

    def get_event(self, event_id: str, *, include_body: bool = False) -> CalendarEvent:
        select = VIEW_SELECT + ",body" if include_body else VIEW_SELECT
        raw = json_body(self._call("GET", f"{GRAPH_BASE}/me/events/{event_id}", params={"$select": select}))
        event = graph_event(raw)
        return graph_body(event, raw) if include_body else event
