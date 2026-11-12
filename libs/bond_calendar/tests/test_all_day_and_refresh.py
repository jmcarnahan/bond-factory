"""All-day drafts in the provider's zone, and the single forced refresh on a 401."""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from bond_calendar import (
    CalendarEventDraft,
    GoogleCalendarProvider,
    MsGraphCalendarProvider,
    ReconnectRequired,
    Unavailable,
)
from bond_calendar.transport import call

LA, SYD = "America/Los_Angeles", "Australia/Sydney"


def local(zone, y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=ZoneInfo(zone))


def make(kind, handler, **kw):
    seen: list[httpx.Request] = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    cls = MsGraphCalendarProvider if kind == "graph" else GoogleCalendarProvider
    if kind == "google":
        kw.pop("timezone", None)  # only Graph takes a zone; shared parametrised tests pass one to both
    return cls(lambda: "tok", httpx.Client(transport=httpx.MockTransport(wrapped)), **kw), seen


def sent(request):
    return httpx.Response(200, content=request.content).json()


def echo_graph(request):
    if request.method == "GET":
        return httpx.Response(200, json={"value": []})
    body = sent(request)
    return httpx.Response(200, json={"id": "e1", "subject": "Day", "isAllDay": True, **{
        k: {"dateTime": body[k]["dateTime"] + ".0000000", "timeZone": body[k]["timeZone"]} for k in ("start", "end")}})


def echo_google(request):
    return httpx.Response(200, json={"id": "g1", "summary": "Day", **sent(request)})


def echo(kind):
    return echo_graph if kind == "graph" else echo_google


def utc_day(d):
    return datetime(2026, 3, d, tzinfo=UTC)


@pytest.mark.parametrize("zone,windows", [(LA, "Pacific Standard Time"), (SYD, "AUS Eastern Standard Time")])
def test_graph_all_day_is_local_midnight_of_the_utc_date_and_round_trips(zone, windows):
    # The shape the tasks mirror builds: UTC midnight start, end = start + 1 day.
    p, seen = make("graph", echo_graph, timezone=zone)
    made = p.create_event(CalendarEventDraft("Day", utc_day(12), utc_day(13), is_all_day=True))
    body = sent(seen[0])
    assert body["isAllDay"] is True
    assert body["start"] == {"dateTime": "2026-03-12T00:00:00", "timeZone": windows}
    assert body["end"] == {"dateTime": "2026-03-13T00:00:00", "timeZone": windows}
    assert made.is_all_day and made.start == utc_day(12) and made.end == utc_day(13)


def test_google_all_day_is_the_utc_date_and_round_trips():
    p, seen = make("google", echo_google)
    made = p.create_event(CalendarEventDraft("Day", utc_day(12), utc_day(13), is_all_day=True))
    assert sent(seen[0])["start"] == {"date": "2026-03-12"} and sent(seen[0])["end"] == {"date": "2026-03-13"}
    assert made.is_all_day and made.start == utc_day(12) and made.end == utc_day(13)


@pytest.mark.parametrize("kind", ["graph", "google"])
def test_all_day_end_is_at_least_the_day_after_the_start(kind):
    p, seen = make(kind, echo(kind), timezone=SYD)
    p.create_event(CalendarEventDraft("Day", utc_day(12), utc_day(12), is_all_day=True))
    body = sent(seen[0])
    end = body["end"].get("dateTime") or body["end"]["date"]
    assert end[:10] == "2026-03-13"


@pytest.mark.parametrize("kind", ["graph", "google"])
def test_utc_default_is_unchanged(kind):
    p, seen = make(kind, echo(kind))
    p.create_event(CalendarEventDraft("Day", datetime(2026, 7, 2, tzinfo=UTC), datetime(2026, 7, 3, tzinfo=UTC),
                                      is_all_day=True))
    body = sent(seen[0])
    if kind == "graph":
        assert body["start"] == {"dateTime": "2026-07-02T00:00:00", "timeZone": "UTC"}
    else:
        assert body["start"] == {"date": "2026-07-02"} and body["end"] == {"date": "2026-07-03"}


@pytest.mark.parametrize("kind", ["graph", "google"])
def test_timed_events_in_a_zone_stay_utc_instants(kind):
    p, seen = make(kind, echo(kind), timezone=LA)
    p.create_event(CalendarEventDraft("Call", local(LA, 2026, 3, 12, 9), local(LA, 2026, 3, 12, 10)))
    expected = "2026-03-12T16:00:00" + ("" if kind == "graph" else "Z")
    assert sent(seen[0])["start"] == {"dateTime": expected, "timeZone": "UTC"}


def run(statuses, refresh):
    seen, answers, counts = [], iter(statuses), {"token": 0, "refresh": 0}

    def handler(request):
        seen.append(request.headers["Authorization"])
        status = next(answers)
        return httpx.Response(status, json={"value": []} if status < 400 else {"error": {"code": "x"}})

    def token():
        counts["token"] += 1
        return "old"

    def fresh():
        counts["refresh"] += 1
        return "new"

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return http, token, (fresh if refresh else None), seen, counts


def test_401_then_200_refreshes_once_and_retries_with_the_new_token():
    http, token, fresh, seen, counts = run([401, 200], True)
    assert call(http, token, "GET", "https://x.example/e", refresh=fresh).status_code == 200
    assert counts == {"token": 1, "refresh": 1} and seen == ["Bearer old", "Bearer new"]


def test_401_then_401_is_reconnect_required_after_one_refresh():
    http, token, fresh, seen, counts = run([401, 401, 200], True)
    with pytest.raises(ReconnectRequired):
        call(http, token, "GET", "https://x.example/e", refresh=fresh)
    assert counts["refresh"] == 1 and len(seen) == 2


def test_401_without_refresh_does_not_retry():
    http, token, _fresh, seen, counts = run([401, 200], False)
    with pytest.raises(ReconnectRequired):
        call(http, token, "GET", "https://x.example/e")
    assert len(seen) == 1 and counts["refresh"] == 0


@pytest.mark.parametrize("status", [500, 429])
def test_a_5xx_or_429_is_not_retried_or_refreshed(status):
    http, token, fresh, seen, counts = run([status, 200], True)
    with pytest.raises(Unavailable):
        call(http, token, "GET", "https://x.example/e", refresh=fresh)
    assert len(seen) == 1 and counts["refresh"] == 0


@pytest.mark.parametrize("kind", ["graph", "google"])
def test_providers_pass_refresh_through(kind):
    answers = iter([401, 200])
    seen = []

    def handler(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(next(answers), json={"id": "x", "summary": "s", "subject": "s"})

    p, _ = make(kind, handler, refresh=lambda: "new")
    p.get_event("x")
    assert seen == ["Bearer tok", "Bearer new"]


@pytest.mark.parametrize("zone", ["Central Europe Standard Time", "Europe/Paris"])
def test_any_zone_name_works_for_reads_and_is_passed_through_for_all_day_writes(zone):
    p, seen = make("graph", echo_graph, timezone=zone)  # no validation at construction
    p.list_events(start=utc_day(1), end=utc_day(2))
    assert seen[0].headers["Prefer"] == f'outlook.timezone="{zone}"'
    p.create_event(CalendarEventDraft("Day", utc_day(12), utc_day(13), is_all_day=True))
    expected = "Romance Standard Time" if zone == "Europe/Paris" else zone
    assert sent(seen[1])["start"] == {"dateTime": "2026-03-12T00:00:00", "timeZone": expected}


def test_unmappable_iana_name_is_passed_through_unchanged():
    p, seen = make("graph", echo_graph, timezone="Pacific/Auckland")
    p.create_event(CalendarEventDraft("Day", utc_day(12), utc_day(13), is_all_day=True))
    assert sent(seen[0])["start"]["timeZone"] == "Pacific/Auckland"


def test_non_string_zone_raises_calendar_error_at_write_time_only():
    from bond_calendar import CalendarError

    p, _ = make("graph", echo_graph, timezone=["x"])
    p.list_events(start=utc_day(1), end=utc_day(2))  # reads still work
    with pytest.raises(CalendarError):
        p.create_event(CalendarEventDraft("Day", utc_day(12), utc_day(13), is_all_day=True))


def test_graph_time_patch_without_is_all_day_is_a_value_error():
    p, seen = make("graph", echo_graph, timezone=LA)
    with pytest.raises(ValueError):
        p.update_event("e1", {"start": utc_day(12)})
    assert seen == []
    p.update_event("e1", {"start": utc_day(12), "end": utc_day(13), "is_all_day": True})
    assert sent(seen[0])["start"]["timeZone"] == "Pacific Standard Time"


def test_a_raising_refresh_becomes_reconnect_required_with_the_cause():
    http, token, _fresh, seen, _counts = run([401, 200], True)

    def boom():
        raise RuntimeError("refresh exploded")

    with pytest.raises(ReconnectRequired) as info:
        call(http, token, "GET", "https://x.example/e", refresh=boom)
    assert isinstance(info.value.__cause__, RuntimeError) and len(seen) == 1


def test_a_refresh_that_raises_a_calendar_error_passes_through_unwrapped():
    http, token, _fresh, seen, _counts = run([401, 200], True)
    original = ReconnectRequired("refresh token revoked")

    def revoked():
        raise original

    with pytest.raises(ReconnectRequired) as info:
        call(http, token, "GET", "https://x.example/e", refresh=revoked)
    assert info.value is original and len(seen) == 1


@pytest.mark.parametrize("kind", ["graph", "google"])
def test_all_day_date_is_the_utc_date_of_a_non_utc_start(kind):
    west = timezone(timedelta(hours=-8))
    start = datetime(2026, 3, 12, 20, tzinfo=west)  # 13 March in UTC
    p, seen = make(kind, echo(kind), timezone=LA)
    p.create_event(CalendarEventDraft("Day", start, start + timedelta(days=1), is_all_day=True))
    body = sent(seen[0])
    if kind == "graph":
        assert body["start"] == {"dateTime": "2026-03-13T00:00:00", "timeZone": "Pacific Standard Time"}
        assert body["end"] == {"dateTime": "2026-03-14T00:00:00", "timeZone": "Pacific Standard Time"}
    else:
        assert body["start"] == {"date": "2026-03-13"} and body["end"] == {"date": "2026-03-14"}
