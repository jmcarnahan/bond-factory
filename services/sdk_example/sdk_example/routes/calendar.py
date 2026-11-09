"""Fake-mode convenience: list the signed-in person's fake calendar events, so the demo can show a mirrored task."""

from __future__ import annotations

from datetime import datetime

from bond_calendar import ReconnectRequired, to_utc
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI, Request

from ..auth_dep import current_user_id
from ..calendar_wiring import event_json, live_connection, provider_for_connection
from ..db import session_scope


def register(app: FastAPI) -> None:
    if app.state.settings.mode != "fake":
        return  # real calendars are read through the provider's own app, not through this demo route

    @app.get("/calendar/events")
    def list_events(request: Request, start: datetime, end: datetime, provider: str = "fake-google",
                    user_id: str = Depends(current_user_id)) -> dict:
        if end <= start:
            raise ApiError("invalid_range", "The end must be after the start.", status=400)
        with session_scope(request.app.state.session_factory) as session:
            connection = live_connection(session, user_id, provider)
            if connection is None:
                raise ApiError("not_connected", "Connect this provider first.", status=404)
            try:
                page = provider_for_connection(request.app, session, connection).list_events(
                    start=to_utc(start), end=to_utc(end))
            except ReconnectRequired as exc:
                raise ApiError("needs_reconnect", exc.message, status=409) from exc
        return {"provider": provider, "events": [event_json(e) for e in page.events], "truncated": page.truncated}
