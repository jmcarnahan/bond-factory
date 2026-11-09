from datetime import UTC, datetime

import httpx
import pytest

from bond_calendar import (
    CalendarError,
    CalendarEventDraft,
    GoogleCalendarProvider,
    MsGraphCalendarProvider,
    NotFound,
)
from bond_calendar.normalize import google_event, graph_event

T0 = datetime(2026, 7, 2, 10, tzinfo=UTC)
T1 = datetime(2026, 7, 2, 11, tzinfo=UTC)


def make(klass, handler):
    seen: list[httpx.Request] = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return klass(lambda: "tok", httpx.Client(transport=httpx.MockTransport(wrapped))), seen


def sent(request):
    return httpx.Response(200, content=request.content).json()


@pytest.mark.parametrize("zone", ["Pacific/Auckland", "Pacific/Kiritimati", "Pacific/Tongatapu", "UTC",
                                  "Pacific Standard Time"])
def test_graph_all_day_keeps_the_wall_date_in_any_zone(zone):
    raw = {"isAllDay": True, "start": {"dateTime": "2026-01-15T00:00:00.0000000", "timeZone": zone},
           "end": {"dateTime": "2026-01-16T00:00:00.0000000", "timeZone": zone}}
    e = graph_event(raw)
    assert e.start == datetime(2026, 1, 15, tzinfo=UTC) and e.end == datetime(2026, 1, 16, tzinfo=UTC)


def test_graph_all_day_utc_expressed_boundary_still_rounds():
    raw = {"isAllDay": True, "start": {"dateTime": "2026-07-24T17:00:00.0000000", "timeZone": "UTC"},
           "end": {"dateTime": "bad", "timeZone": "UTC"}}
    e = graph_event(raw)
    assert e.start == datetime(2026, 7, 25, tzinfo=UTC) and e.end is None


def test_google_all_day_date_is_the_wall_date():
    e = google_event({"start": {"date": "2026-01-15", "timeZone": "Pacific/Auckland"}, "end": {"date": "2026-01-16"}})
    assert e.start == datetime(2026, 1, 15, tzinfo=UTC) and e.is_all_day


def test_graph_update_to_none_clears_the_reminder():
    p, seen = make(MsGraphCalendarProvider, lambda r: httpx.Response(200, json={"id": "e1"}))
    p.update_event("e1", {"reminder_minutes": 15})
    p.update_event("e1", {"reminder_minutes": None})
    assert sent(seen[0]) == {"isReminderOn": True, "reminderMinutesBeforeStart": 15}
    assert sent(seen[1]) == {"isReminderOn": False}


def test_google_update_to_none_clears_the_reminder():
    p, seen = make(GoogleCalendarProvider, lambda r: httpx.Response(200, json={"id": "g1"}))
    p.update_event("g1", {"reminder_minutes": 15})
    p.update_event("g1", {"reminder_minutes": None})
    assert sent(seen[0])["reminders"]["overrides"] == [{"method": "popup", "minutes": 15}]
    assert sent(seen[1]) == {"reminders": {"useDefault": False, "overrides": []}}


@pytest.mark.parametrize("klass", [MsGraphCalendarProvider, GoogleCalendarProvider])
def test_create_without_a_reminder_says_nothing_about_reminders(klass):
    p, seen = make(klass, lambda r: httpx.Response(200, json={"id": "x"}))
    p.create_event(CalendarEventDraft("x", T0, T1))
    assert not {"isReminderOn", "reminders", "reminderMinutesBeforeStart"} & set(sent(seen[0]))


@pytest.mark.parametrize("patch", [{"start": T0}, {"end": T1}, {"start": T0, "end": T1}])
def test_google_time_patch_needs_is_all_day(patch):
    p, seen = make(GoogleCalendarProvider, lambda r: httpx.Response(200, json={"id": "g1"}))
    with pytest.raises(ValueError):
        p.update_event("g1", patch)
    assert seen == []
    p.update_event("g1", {**patch, "is_all_day": False})
    assert "dateTime" in next(v for k, v in sent(seen[0]).items() if k in ("start", "end"))


@pytest.mark.parametrize("klass", [MsGraphCalendarProvider, GoogleCalendarProvider])
def test_malformed_create_answer_is_not_not_found(klass):
    p, _ = make(klass, lambda r: httpx.Response(201, json={}))
    with pytest.raises(CalendarError) as info:
        p.create_event(CalendarEventDraft("x", T0, T1))
    assert not isinstance(info.value, NotFound) and (info.value.status, info.value.code) == (502, "invalid_response")
