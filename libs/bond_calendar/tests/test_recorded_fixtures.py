"""Hand-written payloads in the shape of the public Graph and Google calendar APIs, replayed offline."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from bond_calendar import CalendarEventDraft, Forbidden, GoogleCalendarProvider, MsGraphCalendarProvider

FIX = Path(__file__).parent / "fixtures"
START, END = datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC)


def load(name):
    return json.loads((FIX / name).read_text())


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_graph_calendar_view_replay_two_pages():
    def handler(request):
        if request.method == "GET" and "$skip" in request.url.params:
            return httpx.Response(200, json=load("graph_calendar_view_page2.json"))
        return httpx.Response(200, json=load("graph_calendar_view_page1.json"))

    page = MsGraphCalendarProvider(lambda: "tok", client(handler)).list_events(start=START, end=END)
    assert [e.id for e in page.events] == ["AAMkAGI2example1", "AAMkAGI2example3"]  # cancelled dropped
    first, holiday = page.events
    assert first.subject == "Site visit" and first.location == "Front gate" and first.is_organizer
    assert first.start == datetime(2026, 7, 2, 14, tzinfo=UTC) and first.attendees[0].email == "pat@example.com"
    assert holiday.is_all_day and holiday.start == datetime(2026, 7, 4, tzinfo=UTC)
    assert not page.truncated


def test_graph_include_cancelled_keeps_the_cancelled_event():
    def handler(request):
        if "$skip" in request.url.params:
            return httpx.Response(200, json=load("graph_calendar_view_page2.json"))
        return httpx.Response(200, json=load("graph_calendar_view_page1.json"))

    page = MsGraphCalendarProvider(lambda: "tok", client(handler)).list_events(
        start=START, end=END, include_cancelled=True)
    assert len(page.events) == 3 and page.events[1].is_cancelled


def test_graph_create_replay():
    p = MsGraphCalendarProvider(lambda: "tok", client(lambda r: httpx.Response(201, json=load("graph_event_created.json"))))
    made = p.create_event(CalendarEventDraft("Call", datetime(2026, 7, 6, 10, tzinfo=UTC),
                                              datetime(2026, 7, 6, 10, 30, tzinfo=UTC), reminder_off=True))
    assert made.id == "AAMkAGI2created1" and made.subject == "Call"


def test_graph_403_replay():
    p = MsGraphCalendarProvider(lambda: "tok", client(lambda r: httpx.Response(403, json=load("graph_error_403.json"))))
    try:
        p.get_event("x")
    except Forbidden as exc:
        assert exc.code == "ErrorAccessDenied"
    else:
        raise AssertionError("expected Forbidden")


def test_google_list_replay_two_pages():
    def handler(request):
        if request.url.params.get("pageToken") == "page-two-token":
            return httpx.Response(200, json=load("google_events_page2.json"))
        return httpx.Response(200, json=load("google_events_page1.json"))

    page = GoogleCalendarProvider(lambda: "tok", client(handler)).list_events(start=START, end=END)
    assert [e.id for e in page.events] == ["gevent1", "gevent3"]  # cancelled dropped
    assert page.events[0].etag == '"3181161784712000"' and page.events[1].is_all_day


def test_google_create_replay():
    p = GoogleCalendarProvider(lambda: "tok", client(lambda r: httpx.Response(200, json=load("google_event_created.json"))))
    made = p.create_event(CalendarEventDraft("Call", datetime(2026, 7, 6, 10, tzinfo=UTC),
                                              datetime(2026, 7, 6, 10, 30, tzinfo=UTC)))
    assert made.id == "gcreated1"


def test_google_403_replay():
    p = GoogleCalendarProvider(lambda: "tok", client(lambda r: httpx.Response(403, json=load("google_error_403.json"))))
    try:
        p.get_event("x")
    except Forbidden as exc:
        assert exc.code == "insufficientPermissions"
    else:
        raise AssertionError("expected Forbidden")
