from datetime import UTC, datetime

import httpx
import pytest

from bond_calendar import (
    CalendarError,
    CalendarEventDraft,
    EtagMismatch,
    MsGraphCalendarProvider,
    NotFound,
    ReconnectRequired,
    Unavailable,
)
from bond_calendar.graph import MAX_PAGES, VIEW_SELECT

START = datetime(2026, 7, 1, tzinfo=UTC)
END = datetime(2026, 8, 1, tzinfo=UTC)
BASE = "https://graph.microsoft.com/v1.0"


def provider(handler, **kw):
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped))
    return MsGraphCalendarProvider(lambda: "tok", http, **kw), seen


def ev(n, **over):
    return {"id": f"e{n}", "subject": f"s{n}", "start": {"dateTime": "2026-07-02T10:00:00.0000000", "timeZone": "UTC"},
            "end": {"dateTime": "2026-07-02T11:00:00.0000000", "timeZone": "UTC"}, **over}


def test_list_follows_next_links_over_three_pages():
    def handler(request):
        page = int(request.url.params.get("page", "0")) if request.url.path.endswith("calendarView") else 0
        n = page
        body = {"value": [ev(n * 2), ev(n * 2 + 1)]}
        if n < 2:
            body["@odata.nextLink"] = f"{BASE}/me/calendarView?page={n + 1}&$skiptoken=x"
        return httpx.Response(200, json=body)

    p, seen = provider(handler)
    page = p.list_events(start=START, end=END)
    assert [e.id for e in page.events] == [f"e{i}" for i in range(6)]
    assert page.truncated is False and len(seen) == 3


def test_list_sends_select_orderby_top_and_prefer():
    p, seen = provider(lambda r: httpx.Response(200, json={"value": []}))
    p.list_events(start=START, end=END)
    params = seen[0].url.params
    assert params["$select"] == VIEW_SELECT and params["$orderby"] == "start/dateTime" and params["$top"] == "100"
    assert params["startDateTime"] == "2026-07-01T00:00:00Z"
    assert seen[0].headers["Prefer"] == 'outlook.timezone="UTC"'
    assert seen[0].headers["Authorization"] == "Bearer tok"


def test_next_link_request_has_no_extra_params():
    def handler(request):
        if "skiptoken" in str(request.url):
            return httpx.Response(200, json={"value": [ev(2)]})
        return httpx.Response(200, json={"value": [ev(1)], "@odata.nextLink": f"{BASE}/me/calendarView?$skiptoken=abc"})

    p, seen = provider(handler)
    p.list_events(start=START, end=END)
    assert "$select" not in seen[1].url.params and seen[1].url.params["$skiptoken"] == "abc"


def test_truncated_at_max_events():
    p, _ = provider(lambda r: httpx.Response(200, json={"value": [ev(i) for i in range(5)]}))
    page = p.list_events(start=START, end=END, max_events=3)
    assert len(page.events) == 3 and page.truncated is True


def test_truncated_at_the_page_cap():
    p, seen = provider(lambda r: httpx.Response(200, json={"value": [], "@odata.nextLink": f"{BASE}/me/calendarView?x=1"}))
    page = p.list_events(start=START, end=END)
    assert page.truncated is True and len(seen) == MAX_PAGES


def test_cancelled_dropped_unless_asked():
    p, _ = provider(lambda r: httpx.Response(200, json={"value": [ev(1), ev(2, isCancelled=True)]}))
    assert [e.id for e in p.list_events(start=START, end=END).events] == ["e1"]
    assert len(p.list_events(start=START, end=END, include_cancelled=True).events) == 2


def test_create_posts_utc_body_and_returns_event():
    def handler(request):
        return httpx.Response(201, json=ev(9, **{"@odata.etag": 'W/"a"'}))

    p, seen = provider(handler)
    draft = CalendarEventDraft("Call", datetime(2026, 7, 2, 10, tzinfo=UTC), datetime(2026, 7, 2, 11, tzinfo=UTC),
                               location="Room", body="hi", categories=["x"], attendees=["a@example.com"],
                               reminder_minutes=15)
    event = p.create_event(draft)
    sent = httpx.Response(200, content=seen[0].content).json()
    assert seen[0].method == "POST" and seen[0].url.path == "/v1.0/me/events"
    assert sent["start"] == {"dateTime": "2026-07-02T10:00:00", "timeZone": "UTC"}
    assert sent["attendees"][0]["emailAddress"]["address"] == "a@example.com"
    assert sent["reminderMinutesBeforeStart"] == 15 and sent["body"]["contentType"] == "text"
    assert event.id == "e9" and event.etag == 'W/"a"'


def test_create_without_id_is_an_error():
    p, _ = provider(lambda r: httpx.Response(202))
    with pytest.raises(CalendarError):
        p.create_event(CalendarEventDraft("x", START, END))


def test_update_sends_only_changed_keys_with_if_match():
    p, seen = provider(lambda r: httpx.Response(200, json=ev(1, subject="new")))
    event = p.update_event("e1", {"subject": "new"}, etag='W/"a"')
    assert seen[0].method == "PATCH" and seen[0].headers["If-Match"] == 'W/"a"'
    assert httpx.Response(200, content=seen[0].content).json() == {"subject": "new"}
    assert event.subject == "new"


def test_update_without_etag_sends_no_if_match():
    p, seen = provider(lambda r: httpx.Response(200, json=ev(1)))
    p.update_event("e1", {"location": "Here"})
    assert "If-Match" not in seen[0].headers


def test_update_412_is_etag_mismatch():
    p, _ = provider(lambda r: httpx.Response(412, json={"error": {"code": "PreconditionFailed", "message": "stale"}}))
    with pytest.raises(EtagMismatch) as info:
        p.update_event("e1", {"subject": "x"}, etag='W/"old"')
    assert info.value.status == 412


def test_update_with_empty_answer_rereads_the_event():
    def handler(request):
        return httpx.Response(204) if request.method == "PATCH" else httpx.Response(200, json=ev(1, subject="kept"))

    p, seen = provider(handler)
    assert p.update_event("e1", {"subject": "kept"}).subject == "kept" and [r.method for r in seen] == ["PATCH", "GET"]


def test_update_rejects_unknown_keys():
    p, _ = provider(lambda r: httpx.Response(200, json=ev(1)))
    with pytest.raises(ValueError):
        p.update_event("e1", {"bogus": 1})


@pytest.mark.parametrize("status", [204, 404, 410])
def test_delete_tolerates_gone(status):
    p, seen = provider(lambda r: httpx.Response(status))
    p.delete_event("e1")
    assert seen[0].method == "DELETE" and "If-Match" not in seen[0].headers


def test_get_event_with_body():
    raw = ev(1, body={"contentType": "html", "content": "<p>hi</p>"}, **{"@odata.etag": 'W/"z"'})
    p, seen = provider(lambda r: httpx.Response(200, json=raw))
    event = p.get_event("e1", include_body=True)
    assert seen[0].url.params["$select"].endswith(",body")
    assert (event.body, event.body_content_type, event.etag) == ("<p>hi</p>", "html", 'W/"z"')


def test_get_event_without_body_has_none():
    p, _ = provider(lambda r: httpx.Response(200, json=ev(1)))
    assert p.get_event("e1").body is None


def test_get_404_is_not_found():
    p, _ = provider(lambda r: httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}}))
    with pytest.raises(NotFound):
        p.get_event("nope")


def test_401_is_reconnect_required():
    p, _ = provider(lambda r: httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}}))
    with pytest.raises(ReconnectRequired):
        p.list_events(start=START, end=END)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_server_trouble_is_unavailable(status):
    p, _ = provider(lambda r: httpx.Response(status))
    with pytest.raises(Unavailable):
        p.get_event("e1")


def test_timeout_is_unavailable():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    p, _ = provider(handler)
    with pytest.raises(Unavailable) as info:
        p.list_events(start=START, end=END)
    assert info.value.code == "timeout"


def test_other_4xx_is_a_calendar_error_with_the_provider_code():
    p, _ = provider(lambda r: httpx.Response(403, json={"error": {"code": "ErrorAccessDenied", "message": "no"}}))
    with pytest.raises(CalendarError) as info:
        p.delete_event("e1")
    assert (info.value.status, info.value.code) == (403, "ErrorAccessDenied")


def test_timezone_argument_sets_prefer_header():
    p, seen = provider(lambda r: httpx.Response(200, json={"value": []}), timezone="Pacific Standard Time")
    p.list_events(start=START, end=END)
    assert seen[0].headers["Prefer"] == 'outlook.timezone="Pacific Standard Time"'
