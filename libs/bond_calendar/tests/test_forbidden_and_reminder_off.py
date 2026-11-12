from datetime import UTC, datetime

import httpx
import pytest

from bond_calendar import (
    CalendarError,
    CalendarEventDraft,
    Forbidden,
    GoogleCalendarProvider,
    MsGraphCalendarProvider,
)


def respond(status, body):
    return lambda request: httpx.Response(status, json=body)


def make(klass, handler):
    seen: list[httpx.Request] = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    return klass(lambda: "tok", httpx.Client(transport=httpx.MockTransport(wrapped))), seen


def sent(request):
    import json
    return json.loads(request.content)


DRAFT = {"subject": "Call", "start": datetime(2026, 7, 6, 10, tzinfo=UTC),
         "end": datetime(2026, 7, 6, 10, 30, tzinfo=UTC)}


@pytest.mark.parametrize("klass,body,code", [
    (MsGraphCalendarProvider, {"error": {"code": "ErrorAccessDenied", "message": "no"}}, "ErrorAccessDenied"),
    (GoogleCalendarProvider, {"error": {"code": 403, "message": "scope", "errors": [{"reason": "insufficientPermissions"}]}},
     "insufficientPermissions"),
])
def test_403_raises_forbidden_keeping_the_provider_code(klass, body, code):
    p, _ = make(klass, respond(403, body))
    with pytest.raises(Forbidden) as info:
        p.create_event(CalendarEventDraft(**DRAFT))
    assert (info.value.status, info.value.code) == (403, code)
    assert isinstance(info.value, CalendarError)


def test_403_without_a_body_code_uses_http_403():
    p, _ = make(MsGraphCalendarProvider, lambda r: httpx.Response(403, content=b"nope"))
    with pytest.raises(Forbidden) as info:
        p.get_event("e1")
    assert info.value.code == "http_403"


def test_graph_create_reminder_off():
    p, seen = make(MsGraphCalendarProvider, respond(201, {"id": "e1"}))
    p.create_event(CalendarEventDraft(**DRAFT, reminder_off=True))
    body = sent(seen[0])
    assert body["isReminderOn"] is False and "reminderMinutesBeforeStart" not in body
    assert "reminder_off" not in body


def test_google_create_reminder_off():
    p, seen = make(GoogleCalendarProvider, respond(200, {"id": "g1"}))
    p.create_event(CalendarEventDraft(**DRAFT, reminder_off=True))
    assert sent(seen[0])["reminders"] == {"useDefault": False}


@pytest.mark.parametrize("klass,keys", [
    (MsGraphCalendarProvider, {"isReminderOn", "reminderMinutesBeforeStart", "reminder_off"}),
    (GoogleCalendarProvider, {"reminders", "reminder_off"}),
])
def test_default_draft_payload_unchanged(klass, keys):
    p, seen = make(klass, respond(200, {"id": "x"}))
    p.create_event(CalendarEventDraft(**DRAFT))
    assert not keys & set(sent(seen[0]))


def test_reminder_minutes_wins_over_reminder_off():
    p, seen = make(MsGraphCalendarProvider, respond(201, {"id": "e1"}))
    p.create_event(CalendarEventDraft(**DRAFT, reminder_minutes=10, reminder_off=True))
    assert sent(seen[0])["isReminderOn"] is True and sent(seen[0])["reminderMinutesBeforeStart"] == 10


@pytest.mark.parametrize("klass", [MsGraphCalendarProvider, GoogleCalendarProvider])
def test_reminder_off_is_not_a_patch_key(klass):
    p, _ = make(klass, respond(200, {"id": "x"}))
    with pytest.raises(ValueError):
        p.update_event("x", {"reminder_off": True})


@pytest.mark.parametrize("reason", ["rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded",
                                    "dailyLimitExceeded", "calendarUsageLimitsExceeded"])
def test_google_throttle_403_is_unavailable_with_the_reason_as_code(reason):
    from bond_calendar import Unavailable

    body = {"error": {"code": 403, "message": "slow down", "errors": [{"reason": reason}]}}
    p, _ = make(GoogleCalendarProvider, respond(403, body))
    with pytest.raises(Unavailable) as info:
        p.get_event("e")
    assert not isinstance(info.value, Forbidden)
    assert (info.value.status, info.value.code) == (403, reason)


@pytest.mark.parametrize("reason", ["insufficientPermissions", "forbidden", "notACalendarUser"])
def test_other_google_403_stays_forbidden(reason):
    body = {"error": {"code": 403, "message": "no", "errors": [{"reason": reason}]}}
    p, _ = make(GoogleCalendarProvider, respond(403, body))
    with pytest.raises(Forbidden) as info:
        p.get_event("e")
    assert info.value.code == reason
