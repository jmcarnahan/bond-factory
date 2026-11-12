"""Opt-in live check. Skipped unless BOND_CALENDAR_NETWORK=1 and a token are in the environment.

Set BOND_CALENDAR_PROVIDER to ``graph`` (default) or ``google`` and BOND_CALENDAR_TOKEN to a short-lived access
token for a TEST calendar. It writes one event, edits it, checks a stale etag fails, then deletes it.
Default runs make no network call and never read the token."""

import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bond_calendar import CalendarEventDraft, EtagMismatch, GoogleCalendarProvider, MsGraphCalendarProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("BOND_CALENDAR_NETWORK") != "1" or not os.environ.get("BOND_CALENDAR_TOKEN"),
    reason="live calendar test: set BOND_CALENDAR_NETWORK=1 and BOND_CALENDAR_TOKEN",
)


def test_live_write_edit_stale_etag_delete():
    token = os.environ["BOND_CALENDAR_TOKEN"]
    klass = GoogleCalendarProvider if os.environ.get("BOND_CALENDAR_PROVIDER") == "google" else MsGraphCalendarProvider
    provider = klass(lambda: token, httpx.Client(timeout=20))
    start = datetime.now(UTC).replace(microsecond=0, second=0) + timedelta(days=30)
    made = provider.create_event(CalendarEventDraft("bond_calendar live check", start, start + timedelta(minutes=15),
                                                    reminder_off=True))
    try:
        edited = provider.update_event(made.id, {"subject": "bond_calendar live check (edited)"}, etag=made.etag)
        assert edited.subject.endswith("(edited)")
        if made.etag:
            with pytest.raises(EtagMismatch):
                provider.update_event(made.id, {"subject": "stale"}, etag=made.etag)
        window = provider.list_events(start=start - timedelta(hours=1), end=start + timedelta(hours=1))
        assert any(e.id == made.id for e in window.events)
    finally:
        provider.delete_event(made.id)
