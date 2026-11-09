"""Calendar providers for the example app: one provider per OAuth connection.

Fake mode: a `FakeCalendarProvider` per connection id on `app.state.fake_calendars`, so events persist across requests
and a task mirror can show an external id. Real mode: the Graph or Google provider whose token comes from
`bond_oauth.access_token` for that connection. The provider borrows `session`, so use it inside the same
`session_scope` block that loaded the connection.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any

import bond_calendar as cal
import bond_oauth as oauth
import httpx
from fastapi import FastAPI
from sqlalchemy.orm import Session

from .models.connections import OAuthConnection
from .oauth_wiring import OAuthWiring

REAL_PROVIDERS = ("google", "microsoft")


def live_connection(session: Session, user_id: str, provider_name: str) -> OAuthConnection | None:
    """The person's live (not revoked) connection for a registered provider name, if any."""
    return (session.query(OAuthConnection)
            .filter_by(user_id=user_id, provider=provider_name, revoked_at=None).first())


def fake_calendars(app: FastAPI) -> dict[str, cal.FakeCalendarProvider]:
    if getattr(app.state, "fake_calendars", None) is None:
        app.state.fake_calendars = {}
    return app.state.fake_calendars


def _http(app: FastAPI) -> httpx.Client:
    if getattr(app.state, "calendar_http", None) is None:
        app.state.calendar_http = httpx.Client(timeout=15)
    return app.state.calendar_http


def token_for(session: Session, connection: OAuthConnection, wiring: OAuthWiring):
    """A `token()` callable for the lib: oauth failures become the calendar lib's typed errors."""

    def token() -> str:
        try:
            return oauth.access_token(session, connection, provider=wiring.providers[connection.provider],
                                      cipher=wiring.cipher)
        except oauth.ReconnectRequired as exc:
            raise cal.ReconnectRequired(str(exc) or "The calendar connection must be re-authorised.") from exc
        except oauth.RetryableError as exc:
            raise cal.Unavailable(str(exc) or "The calendar sign-in is unavailable.") from exc

    return token


def provider_for_connection(app: FastAPI, session: Session, connection: OAuthConnection) -> cal.CalendarProvider:
    if app.state.settings.mode == "fake":
        # The fake has no token to refuse, so the connection's own state stands in for it: a revoked row or one that
        # needs a reconnect (simulate-expiry) refuses like a real calendar would, and the mirror marks the task skipped.
        if connection.revoked_at is not None or connection.last_error:
            raise cal.ReconnectRequired("The calendar connection must be re-authorised.")
        # One id prefix per connection, so a reconnect never reuses an external event id.
        return fake_calendars(app).setdefault(
            connection.id, cal.FakeCalendarProvider(id_prefix=f"fake-{connection.id[:8]}"))
    token = token_for(session, connection, app.state.oauth)
    if connection.provider == "google":
        return cal.GoogleCalendarProvider(token, _http(app))
    if connection.provider == "microsoft":
        return cal.MsGraphCalendarProvider(token, _http(app), timezone="UTC")
    raise ValueError(f"no calendar provider for connection provider {connection.provider!r}")


def _z(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def event_json(event: cal.CalendarEvent) -> dict[str, Any]:
    """A `CalendarEvent` as plain JSON: instants as `Z` strings, nested people as dicts."""
    data = dataclasses.asdict(event)
    data["start"], data["end"] = _z(event.start), _z(event.end)
    return data
