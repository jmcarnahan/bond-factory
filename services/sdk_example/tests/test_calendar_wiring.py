from datetime import UTC, datetime
from types import SimpleNamespace

import bond_calendar as cal
import bond_oauth as oauth
import httpx
import pytest
from connections_util import connect, headers
from fastapi.testclient import TestClient

from sdk_example import calendar_wiring
from sdk_example.models.auth import VIEWER_USER_ID
from sdk_example.models.connections import OAuthConnection

WINDOW = {"start": "2026-07-01T00:00:00Z", "end": "2026-08-01T00:00:00Z"}
T0, T1 = datetime(2026, 7, 2, 10, tzinfo=UTC), datetime(2026, 7, 2, 11, tzinfo=UTC)


def connection_row(app, provider="fake-google"):
    with app.state.session_factory() as session:
        row = session.query(OAuthConnection).filter_by(provider=provider, revoked_at=None).one()
        session.expunge(row)
        return row


def test_events_route_needs_a_session(client):
    assert client.get("/calendar/events", params=WINDOW).status_code == 401


def test_events_route_without_a_connection_is_404(client):
    reply = client.get("/calendar/events", params=WINDOW, headers=headers(client))
    assert reply.status_code == 404 and reply.json()["detail"]["code"] == "not_connected"


def test_events_route_rejects_an_empty_range(client):
    h = headers(client)
    connect(client, h)
    reply = client.get("/calendar/events", params={"start": WINDOW["end"], "end": WINDOW["start"]}, headers=h)
    assert reply.status_code == 400


def test_connected_calendar_starts_empty_and_shows_a_created_event(app, client):
    h = headers(client)
    connect(client, h)
    assert client.get("/calendar/events", params=WINDOW, headers=h).json()["events"] == []
    with app.state.session_factory() as session:
        row = session.query(OAuthConnection).filter_by(provider="fake-google", revoked_at=None).one()
        made = calendar_wiring.provider_for_connection(app, session, row).create_event(
            cal.CalendarEventDraft("Mirrored task", T0, T1))
    body = client.get("/calendar/events", params=WINDOW, headers=h).json()
    assert [(e["id"], e["subject"], e["start"]) for e in body["events"]] == [(made.id, "Mirrored task", "2026-07-02T10:00:00Z")]
    assert body["events"][0]["etag"] == made.etag and body["truncated"] is False


def test_fake_provider_is_kept_per_connection_across_calls(app, client):
    h = headers(client)
    connect(client, h)
    row = connection_row(app)
    with app.state.session_factory() as session:
        first = calendar_wiring.provider_for_connection(app, session, row)
        second = calendar_wiring.provider_for_connection(app, session, row)
    assert first is second and app.state.fake_calendars[row.id] is first and isinstance(first, cal.FakeCalendarProvider)


def test_each_provider_connection_has_its_own_calendar(app, client):
    h = headers(client)
    connect(client, h, "fake-google")
    connect(client, h, "fake-microsoft")
    google, microsoft = connection_row(app, "fake-google"), connection_row(app, "fake-microsoft")
    with app.state.session_factory() as session:
        calendar_wiring.provider_for_connection(app, session, google).create_event(cal.CalendarEventDraft("g", T0, T1))
    on_google = client.get("/calendar/events", params=WINDOW, headers=h).json()["events"]
    on_microsoft = client.get("/calendar/events", params={**WINDOW, "provider": "fake-microsoft"}, headers=h).json()["events"]
    assert len(on_google) == 1 and on_microsoft == [] and google.id != microsoft.id


def test_another_person_does_not_see_the_calendar(client):
    connect(client, headers(client))
    other = TestClient(client.app)
    reply = other.get("/calendar/events", params=WINDOW, headers=headers(other, VIEWER_USER_ID))
    assert reply.status_code == 404


def test_expired_or_revoked_connection_refuses_in_fake_mode(app, client):
    h = headers(client)
    connect(client, h)
    assert client.post("/connections/fake-google/simulate-expiry", headers=h).status_code == 200
    row = connection_row(app)
    assert row.last_error
    with app.state.session_factory() as session, pytest.raises(cal.ReconnectRequired):
        calendar_wiring.provider_for_connection(app, session, row)
    revoked = SimpleNamespace(id=row.id, provider=row.provider, last_error=None, revoked_at=T0)
    with app.state.session_factory() as session, pytest.raises(cal.ReconnectRequired):
        calendar_wiring.provider_for_connection(app, session, revoked)


def test_fake_event_ids_differ_between_connections(app, client):
    h = headers(client)
    connect(client, h)
    first = connection_row(app)
    connect(client, h)  # a reconnect revokes the old row and inserts a new one
    second = connection_row(app)
    ids = []
    for row in (first, second):
        with app.state.session_factory() as session:
            ids.append(calendar_wiring.provider_for_connection(app, session, row).create_event(
                cal.CalendarEventDraft("x", T0, T1)).id)
    assert first.id != second.id and ids[0] != ids[1] and all(i.startswith("fake-") for i in ids)


def real_app(handler, provider="google"):
    wiring = SimpleNamespace(providers={provider: object()}, cipher=object())
    state = SimpleNamespace(settings=SimpleNamespace(mode="real"), oauth=wiring,
                            calendar_http=httpx.Client(transport=httpx.MockTransport(handler)))
    return SimpleNamespace(state=state), SimpleNamespace(id="c1", provider=provider)


@pytest.mark.parametrize(("name", "klass"), [("google", cal.GoogleCalendarProvider),
                                              ("microsoft", cal.MsGraphCalendarProvider)])
def test_real_mode_builds_the_matching_provider_with_the_oauth_token(monkeypatch, name, klass):
    seen = []
    monkeypatch.setattr(oauth, "access_token", lambda session, connection, **kw: "oauth-token")
    app, row = real_app(lambda r: seen.append(r) or httpx.Response(200, json={"value": [], "items": []}), name)
    provider = calendar_wiring.provider_for_connection(app, None, row)
    provider.list_events(start=T0, end=T1)
    assert isinstance(provider, klass) and seen[0].headers["Authorization"] == "Bearer oauth-token"


def test_real_mode_translates_oauth_failures_to_calendar_errors(monkeypatch):
    app, row = real_app(lambda r: httpx.Response(200, json={"items": []}))
    provider = calendar_wiring.provider_for_connection(app, None, row)

    def refuse(*a, **kw):
        raise oauth.ReconnectRequired("invalid_grant")

    monkeypatch.setattr(oauth, "access_token", refuse)
    with pytest.raises(cal.ReconnectRequired):
        provider.list_events(start=T0, end=T1)

    def wobble(*a, **kw):
        raise oauth.RetryableError("timeout")

    monkeypatch.setattr(oauth, "access_token", wobble)
    with pytest.raises(cal.Unavailable):
        provider.list_events(start=T0, end=T1)


def test_unknown_real_provider_is_a_value_error():
    app, row = real_app(lambda r: httpx.Response(200), "other")
    with pytest.raises(ValueError):
        calendar_wiring.provider_for_connection(app, None, row)
