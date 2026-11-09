"""Graph and Google event payloads to ``CalendarEvent``. Tolerant: a missing or odd field never raises."""

from __future__ import annotations

from typing import Any

from .models import Attendee, CalendarEvent, Person
from .times import all_day_boundary, parse_day, parse_instant

PREVIEW_CHARS = 255


def _person(entry: Any) -> Person | None:
    addr = (entry or {}).get("emailAddress") or {}
    name, email = addr.get("name"), addr.get("address")
    return Person(name, email) if (name or email) else None


def graph_event(raw: dict[str, Any]) -> CalendarEvent:
    all_day = bool(raw.get("isAllDay"))
    start_block, end_block = raw.get("start") or {}, raw.get("end") or {}
    if all_day:  # the wall date in the event's own zone, never an instant (see all_day_boundary)
        start, end = all_day_boundary(start_block.get("dateTime")), all_day_boundary(end_block.get("dateTime"))
    else:
        start = parse_instant(start_block.get("dateTime"), start_block.get("timeZone"))
        end = parse_instant(end_block.get("dateTime"), end_block.get("timeZone"))
    attendees = []
    for a in raw.get("attendees") or []:
        addr = (a.get("emailAddress") or {}) if isinstance(a, dict) else {}
        attendees.append(Attendee(addr.get("name"), addr.get("address"), a.get("type"),
                                  (a.get("status") or {}).get("response")))
    join = (raw.get("onlineMeeting") or {}).get("joinUrl") or None
    return CalendarEvent(
        id=raw.get("id") or "", etag=raw.get("@odata.etag"), subject=raw.get("subject"), start=start, end=end,
        is_all_day=all_day, location=(raw.get("location") or {}).get("displayName") or None,
        organizer=_person(raw.get("organizer")), attendees=attendees, is_organizer=bool(raw.get("isOrganizer")),
        is_online_meeting=bool(raw.get("isOnlineMeeting")), join_url=join, show_as=raw.get("showAs"),
        is_cancelled=bool(raw.get("isCancelled")), series_master_id=raw.get("seriesMasterId"),
        event_type=raw.get("type"), preview=raw.get("bodyPreview"), web_link=raw.get("webLink"),
        response_status=(raw.get("responseStatus") or {}).get("response"), sensitivity=raw.get("sensitivity"),
        categories=list(raw.get("categories") or []),
    )


def graph_body(event: CalendarEvent, raw: dict[str, Any]) -> CalendarEvent:
    """Attach the full body of a single-event read."""
    block = raw.get("body") or {}
    event.body = block.get("content") or ""
    event.body_content_type = "html" if str(block.get("contentType") or "").lower() == "html" else "text"
    return event


_GOOGLE_RESPONSE = {"accepted": "accepted", "declined": "declined", "tentative": "tentativelyAccepted",
                    "needsAction": "notResponded"}
_GOOGLE_VISIBILITY = {"private": "private", "confidential": "confidential"}


def google_is_dropped(raw: dict[str, Any]) -> bool:
    """Cancelled events and events the signed-in person declined are not shown."""
    if raw.get("status") == "cancelled":
        return True
    return any(isinstance(a, dict) and a.get("self") and a.get("responseStatus") == "declined"
               for a in raw.get("attendees") or [])


def _google_time(block: dict[str, Any]):
    if block.get("dateTime"):
        return parse_instant(block["dateTime"], block.get("timeZone")), False
    if block.get("date"):
        return parse_day(block["date"]), True
    return None, False


def google_event(raw: dict[str, Any]) -> CalendarEvent:
    start, all_day = _google_time(raw.get("start") or {})
    end, _ = _google_time(raw.get("end") or {})
    organizer = raw.get("organizer") or {}
    attendees, mine = [], None
    for a in raw.get("attendees") or []:
        if not isinstance(a, dict):
            continue
        response = _GOOGLE_RESPONSE.get(a.get("responseStatus") or "", a.get("responseStatus"))
        kind = "resource" if a.get("resource") else "optional" if a.get("optional") else "required"
        attendees.append(Attendee(a.get("displayName"), a.get("email"), kind, response))
        if a.get("self"):
            mine = response
    is_org = bool(organizer.get("self"))
    join = raw.get("hangoutLink") or next((e.get("uri") for e in (raw.get("conferenceData") or {}).get(
        "entryPoints") or [] if isinstance(e, dict) and e.get("entryPointType") == "video"), None)
    description = raw.get("description")
    return CalendarEvent(
        id=raw.get("id") or "", etag=raw.get("etag"), subject=raw.get("summary"), start=start, end=end,
        is_all_day=all_day, location=raw.get("location") or None,
        organizer=Person(organizer.get("displayName"), organizer.get("email")) if organizer else None,
        attendees=attendees, is_organizer=is_org, is_online_meeting=bool(join), join_url=join,
        show_as="free" if raw.get("transparency") == "transparent" else "busy",
        is_cancelled=raw.get("status") == "cancelled", series_master_id=raw.get("recurringEventId"),
        event_type="occurrence" if raw.get("recurringEventId") else "singleInstance",
        preview=description[:PREVIEW_CHARS] if isinstance(description, str) else None,
        web_link=raw.get("htmlLink"), response_status="organizer" if is_org and mine is None else mine,
        sensitivity=_GOOGLE_VISIBILITY.get(raw.get("visibility") or "", "normal"), categories=[],
    )


def google_body(event: CalendarEvent, raw: dict[str, Any]) -> CalendarEvent:
    description = raw.get("description")
    event.body = description if isinstance(description, str) else ""
    event.body_content_type = "html" if "<" in event.body and ">" in event.body else "text"
    return event
