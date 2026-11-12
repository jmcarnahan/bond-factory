from datetime import UTC, datetime

import httpx
import pytest

from bond_calendar import (
    CalendarEventDraft,
    FakeCalendarProvider,
    GoogleCalendarProvider,
    MsGraphCalendarProvider,
    Person,
)

T0, T1 = datetime(2026, 7, 2, 10, tzinfo=UTC), datetime(2026, 7, 2, 11, tzinfo=UTC)


def _sent(factory, draft, **kw):
    seen = []

    def handler(request):
        seen.append(httpx.Response(200, content=request.content).json())
        return httpx.Response(200, json={"id": "x"})

    p = factory(lambda: "tok", httpx.Client(transport=httpx.MockTransport(handler)))
    p.create_event(draft)
    return seen[0]


def _draft(attendees):
    return CalendarEventDraft("Call", T0, T1, attendees=attendees)


def test_graph_writes_a_display_name_and_keeps_a_plain_string():
    sent = _sent(MsGraphCalendarProvider, _draft(["a@example.com", Person("Pat Example", "pat@example.com")]))
    assert sent["attendees"] == [
        {"emailAddress": {"address": "a@example.com"}, "type": "required"},
        {"emailAddress": {"address": "pat@example.com", "name": "Pat Example"}, "type": "required"},
    ]


def test_google_writes_a_display_name_and_keeps_a_plain_string():
    sent = _sent(GoogleCalendarProvider, _draft(["a@example.com", Person("Pat Example", "pat@example.com")]))
    assert sent["attendees"] == [{"email": "a@example.com"},
                                 {"email": "pat@example.com", "displayName": "Pat Example"}]


def test_a_person_with_no_name_is_written_as_a_plain_address():
    sent = _sent(GoogleCalendarProvider, _draft([Person(None, "a@example.com")]))
    assert sent["attendees"] == [{"email": "a@example.com"}]


def test_a_person_with_no_address_is_refused():
    with pytest.raises(ValueError):
        _sent(MsGraphCalendarProvider, _draft([Person("No Address")]))


def test_a_patch_takes_persons_too():
    seen = []

    def handler(request):
        seen.append(httpx.Response(200, content=request.content).json())
        return httpx.Response(200, json={"id": "x"})

    p = GoogleCalendarProvider(lambda: "tok", httpx.Client(transport=httpx.MockTransport(handler)))
    p.update_event("x", {"attendees": [Person("Pat Example", "pat@example.com")]})
    assert seen[0]["attendees"] == [{"email": "pat@example.com", "displayName": "Pat Example"}]


def test_the_fake_keeps_the_display_name():
    fake = FakeCalendarProvider()
    event = fake.create_event(_draft([Person("Pat Example", "pat@example.com"), "b@example.com"]))
    assert [(a.name, a.email) for a in event.attendees] == [("Pat Example", "pat@example.com"), (None, "b@example.com")]
    fake.update_event(event.id, {"attendees": [Person("Lee Example", "lee@example.com")]})
    assert fake.events[0].attendees[0].name == "Lee Example"
