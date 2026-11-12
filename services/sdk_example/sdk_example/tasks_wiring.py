"""Wires bond_tasks_py into the example: the calendar mirror and the helpers the routes share.

    MirrorProviders the lib's `MirrorProviders` over the user's live OAuth connection and `calendar_wiring`
    install(app)    builds them and the TODO wiring (`todo_wiring.py`: preferences, inbox, push, capture)
    user_names, user_exists   the two lookups the lib's service takes

Notices are not made here: the sweep (`sweep_wiring.py`) claims them and the inbox stores them.
"""

from __future__ import annotations

from typing import Any

import bond_calendar as cal
from bond_tasks_py.protocols import MirrorDraft
from fastapi import FastAPI

from . import calendar_wiring, todo_wiring
from .db import session_scope
from .models.auth import User
from .models.connections import OAuthConnection
from .oauth_wiring import FAKE_GOOGLE, FAKE_MICROSOFT
from .settings import Settings

#: registered OAuth provider name -> the label stored in tasks.external_provider
LABELS = {FAKE_GOOGLE: "google", FAKE_MICROSOFT: "microsoft", "google": "google", "microsoft": "microsoft"}
ORDER = {"fake": (FAKE_GOOGLE, FAKE_MICROSOFT), "real": ("google", "microsoft")}


class _SessionMirror:
    """A `CalendarMirror` that opens its own session per call (the real providers borrow one for the token)."""

    def __init__(self, app: FastAPI, connection_id: str) -> None:
        self.app, self.connection_id = app, connection_id

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        with session_scope(self.app.state.session_factory) as session:
            row = session.get(OAuthConnection, self.connection_id)
            if row is None or row.revoked_at is not None:
                raise cal.ReconnectRequired("The calendar connection is gone.")
            provider = calendar_wiring.provider_for_connection(self.app, session, row)
            return getattr(provider, name)(*args, **kwargs)

    def create_event(self, draft: MirrorDraft) -> Any:
        return self._call("create_event", cal.CalendarEventDraft(
            subject=draft.subject, start=draft.start, end=draft.end, is_all_day=draft.is_all_day,
            location=draft.location, body=draft.body, body_type=draft.body_type,
            categories=list(draft.categories), reminder_minutes=draft.reminder_minutes))

    def update_event(self, event_id: str, patch: dict, *, etag: str | None = None) -> Any:
        patch = {**patch, "categories": list(patch.get("categories") or [])}
        return self._call("update_event", event_id, patch, etag=etag)

    def delete_event(self, event_id: str) -> None:
        self._call("delete_event", event_id)

    def get_event(self, event_id: str) -> Any:
        return self._call("get_event", event_id)


class MirrorProviders:
    """`for_user`: the person's live connection (Google first, then Microsoft), or None."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def for_user(self, session: Any, user_id: str) -> tuple[str, _SessionMirror] | None:
        settings: Settings = self.app.state.settings
        for name in ORDER["fake" if settings.mode == "fake" else "real"]:
            connection = calendar_wiring.live_connection(session, user_id, name)
            if connection is not None:
                return LABELS[name], _SessionMirror(self.app, connection.id)
        return None


def install(app: FastAPI) -> None:
    """Idempotent. Builds the calendar-mirror providers and the TODO wiring (preferences, inbox, push, capture)."""
    if getattr(app.state, "mirror_providers", None) is not None:
        return
    app.state.mirror_providers = MirrorProviders(app)
    todo_wiring.install(app)


def user_names(session: Any):
    """A `names` callable for the lib's serializer: user id to display name."""

    def names(ids: list[str]) -> dict[str, str]:
        rows = session.query(User).filter(User.id.in_(ids)).all()
        return {u.id: u.name or u.email for u in rows}

    return names


def user_exists(session: Any):
    def exists(user_id: str) -> bool:
        user = session.get(User, user_id)
        return user is not None and bool(user.is_active)

    return exists
