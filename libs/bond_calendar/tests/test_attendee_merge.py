"""Duplicate attendees merge by lower-cased address; a nameless Person is an ``InvalidAttendee``."""

import pytest
from test_person_attendees import T0, T1, _draft, _sent

from bond_calendar import (
    CalendarError,
    CalendarEventDraft,
    FakeCalendarProvider,
    GoogleCalendarProvider,
    InvalidAttendee,
    MsGraphCalendarProvider,
    Person,
)
from bond_calendar.models import merged_attendees


def test_merge_keeps_order_and_lets_a_named_entry_win():
    named = Person("Pat Example", "Pat@example.com")
    out = merged_attendees(["a@example.com", "pat@example.com", named, "A@example.com", Person("Other", "pat@example.com")])
    assert out == ["a@example.com", named]  # the first named entry for an address wins
    assert merged_attendees(None) == [] and merged_attendees([]) == []
    assert merged_attendees([Person(None, "x@example.com"), "X@example.com"]) == [Person(None, "x@example.com")]


@pytest.mark.parametrize("factory", [MsGraphCalendarProvider, GoogleCalendarProvider])
def test_providers_send_one_entry_per_address(factory):
    sent = _sent(factory, _draft(["pat@example.com", Person("Pat Example", "PAT@example.com")]))
    key = "attendees"
    assert len(sent[key]) == 1
    assert "Pat Example" in str(sent[key][0])


def test_fake_provider_merges_on_create_and_patch():
    fake = FakeCalendarProvider()
    event = fake.create_event(CalendarEventDraft("Call", T0, T1, attendees=["a@example.com", Person("Ann", "A@example.com")]))
    got = fake.get_event(event.id)
    assert [(a.name, a.email) for a in got.attendees] == [("Ann", "A@example.com")]
    patched = fake.update_event(event.id, {"attendees": ["b@example.com", "B@example.com"]})
    assert [a.email for a in patched.attendees] == ["b@example.com"]


@pytest.mark.parametrize("factory", [MsGraphCalendarProvider, GoogleCalendarProvider])
def test_a_person_without_an_address_is_invalid_attendee(factory):
    with pytest.raises(InvalidAttendee) as info:
        _sent(factory, _draft([Person("No Address")]))
    assert isinstance(info.value, CalendarError) and info.value.status == 422
    assert info.value.code == "invalid_attendee"


def test_fake_provider_and_patch_raise_invalid_attendee():
    fake = FakeCalendarProvider()
    with pytest.raises(InvalidAttendee):
        fake.create_event(CalendarEventDraft("Call", T0, T1, attendees=[Person("N", None)]))
    ok = fake.create_event(CalendarEventDraft("Call", T0, T1))
    with pytest.raises(InvalidAttendee):
        fake.update_event(ok.id, {"attendees": [Person("N", "")]})
