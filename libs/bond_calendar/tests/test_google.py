from datetime import UTC, datetime

import httpx
import pytest

from bond_calendar import (
    CalendarEventDraft,
    EtagMismatch,
    GoogleCalendarProvider,
    NotFound,
    ReconnectRequired,
    Unavailable,
)
from bond_calendar.google import EVENTS_URL, LIST_FIELDS

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 8, 1, tzinfo=UTC)


def provider(handler):
    seen: list[httpx.Request] = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return GoogleCalendarProvider(lambda: "tok", httpx.Client(transport=httpx.MockTransport(wrapped))), seen


def gev(n, **over):
    return {"id": f"g{n}", "etag": f'"{n}"', "summary": f"s{n}", "status": "confirmed",
            "start": {"dateTime": "2026-07-02T10:00:00-07:00"}, "end": {"dateTime": "2026-07-02T11:00:00-07:00"},
            **over}


def test_list_sends_query_parameters():
    p, seen = provider(lambda r: httpx.Response(200, json={"items": []}))
    p.list_events(start=START, end=END, max_events=50)
    q = seen[0].url.params
    assert str(seen[0].url).startswith(EVENTS_URL)
    assert (q["timeMin"], q["timeMax"]) == ("2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z")
    assert q["singleEvents"] == "true" and q["orderBy"] == "startTime" and q["maxResults"] == "50"
    assert q["fields"] == LIST_FIELDS and seen[0].headers["Authorization"] == "Bearer tok"


def test_list_follows_page_tokens():
    def handler(request):
        token = request.url.params.get("pageToken")
        if token is None:
            return httpx.Response(200, json={"items": [gev(1)], "nextPageToken": "t2"})
        if token == "t2":
            return httpx.Response(200, json={"items": [gev(2)], "nextPageToken": "t3"})
        return httpx.Response(200, json={"items": [gev(3)]})

    p, seen = provider(handler)
    page = p.list_events(start=START, end=END)
    assert [e.id for e in page.events] == ["g1", "g2", "g3"] and len(seen) == 3 and not page.truncated


def test_list_truncates_at_max_events():
    p, _ = provider(lambda r: httpx.Response(200, json={"items": [gev(i) for i in range(4)]}))
    page = p.list_events(start=START, end=END, max_events=2)
    assert len(page.events) == 2 and page.truncated


def test_cancelled_and_self_declined_are_dropped():
    items = [
        gev(1),
        gev(2, status="cancelled"),
        gev(3, attendees=[{"email": "me@example.com", "self": True, "responseStatus": "declined"}]),
        gev(4, attendees=[{"email": "x@example.com", "responseStatus": "declined"}]),  # someone else declined
        gev(5, attendees=[{"email": "me@example.com", "self": True, "responseStatus": "accepted"}]),
    ]
    p, _ = provider(lambda r: httpx.Response(200, json={"items": items}))
    assert [e.id for e in p.list_events(start=START, end=END).events] == ["g1", "g4", "g5"]


def test_include_cancelled_asks_for_deleted_and_keeps_them():
    p, seen = provider(lambda r: httpx.Response(200, json={"items": [gev(1, status="cancelled")]}))
    page = p.list_events(start=START, end=END, include_cancelled=True)
    assert seen[0].url.params["showDeleted"] == "true" and page.events[0].is_cancelled


def test_create_posts_a_timed_event():
    p, seen = provider(lambda r: httpx.Response(200, json=gev(1)))
    p.create_event(CalendarEventDraft("Call", datetime(2026, 7, 2, 10, tzinfo=UTC), datetime(2026, 7, 2, 11, tzinfo=UTC),
                                      location="Room", body="notes", attendees=["a@example.com"], reminder_minutes=10))
    sent = httpx.Response(200, content=seen[0].content).json()
    assert seen[0].method == "POST"
    assert sent["start"] == {"dateTime": "2026-07-02T10:00:00Z", "timeZone": "UTC"}
    assert sent["summary"] == "Call" and sent["description"] == "notes" and sent["attendees"] == [{"email": "a@example.com"}]
    assert sent["reminders"]["overrides"][0]["minutes"] == 10


def test_create_all_day_sends_dates():
    p, seen = provider(lambda r: httpx.Response(200, json=gev(1)))
    p.create_event(CalendarEventDraft("Day", datetime(2026, 7, 2, tzinfo=UTC), datetime(2026, 7, 3, tzinfo=UTC),
                                      is_all_day=True))
    sent = httpx.Response(200, content=seen[0].content).json()
    assert sent["start"] == {"date": "2026-07-02"} and sent["end"] == {"date": "2026-07-03"}


def test_update_patches_changed_keys_with_if_match():
    p, seen = provider(lambda r: httpx.Response(200, json=gev(1, summary="new")))
    event = p.update_event("g1", {"subject": "new"}, etag='"1"')
    assert seen[0].method == "PATCH" and seen[0].headers["If-Match"] == '"1"' and seen[0].url.path.endswith("/g1")
    assert httpx.Response(200, content=seen[0].content).json() == {"summary": "new"}
    assert event.subject == "new"


def test_update_412_is_etag_mismatch():
    p, _ = provider(lambda r: httpx.Response(412, json={"error": {"code": 412, "message": "x"}}))
    with pytest.raises(EtagMismatch):
        p.update_event("g1", {"subject": "x"}, etag='"old"')


@pytest.mark.parametrize("status", [204, 404, 410])
def test_delete_tolerates_gone(status):
    p, seen = provider(lambda r: httpx.Response(status))
    p.delete_event("g1")
    assert seen[0].method == "DELETE"


def test_get_event_returns_body_when_asked():
    p, seen = provider(lambda r: httpx.Response(200, json=gev(1, description="plain notes")))
    event = p.get_event("g1", include_body=True)
    assert (event.body, event.body_content_type, event.etag) == ("plain notes", "text", '"1"')
    assert p.get_event("g1").body is None and seen[0].url.params["fields"]


def test_get_404_is_not_found():
    p, _ = provider(lambda r: httpx.Response(404, json={"error": {"code": 404, "message": "Not Found"}}))
    with pytest.raises(NotFound):
        p.get_event("nope")


def test_401_is_reconnect_required():
    p, _ = provider(lambda r: httpx.Response(401, json={"error": {"code": 401}}))
    with pytest.raises(ReconnectRequired):
        p.list_events(start=START, end=END)


def test_403_keeps_the_google_reason_as_the_code():
    body = {"error": {"code": 403, "message": "scope", "errors": [{"reason": "insufficientPermissions"}]}}
    p, _ = provider(lambda r: httpx.Response(403, json=body))
    with pytest.raises(Exception) as info:
        p.create_event(CalendarEventDraft("x", START, END))
    assert (info.value.status, info.value.code) == (403, "insufficientPermissions")


@pytest.mark.parametrize("status", [429, 500, 503])
def test_server_trouble_is_unavailable(status):
    p, _ = provider(lambda r: httpx.Response(status))
    with pytest.raises(Unavailable):
        p.list_events(start=START, end=END)


def test_transport_failure_is_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    p, _ = provider(handler)
    with pytest.raises(Unavailable):
        p.get_event("g1")
