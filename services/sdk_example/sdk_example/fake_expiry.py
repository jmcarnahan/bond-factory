"""DELETE in an app without connections (and in any real deployment). Fake mode only: make the provider refuse the
stored grant, so a person can see the "reconnect" state without waiting for a real revocation."""

from __future__ import annotations

from collections.abc import Callable

import bond_oauth as oauth
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI

from .connect_helpers import status_json, status_of
from .db import session_scope
from .models.connections import OAuthConnection
from .oauth_wiring import OAuthWiring


def register_expiry(app: FastAPI, wiring: OAuthWiring, provider_or_404: Callable, manage: Callable,
                    hook: Callable) -> None:
    factory = app.state.session_factory

    @app.post("/connections/{provider}/simulate-expiry")
    def simulate_expiry(provider: str, user_id: str = Depends(manage)) -> dict:
        provider_or_404(provider)
        fake = wiring.fakes[provider]
        with session_scope(factory) as session:
            rows = session.query(OAuthConnection).filter_by(user_id=user_id, provider=provider, revoked_at=None).all()
            if not rows:
                raise ApiError("not_connected", "Connect this provider first.", status=404)
            fake.fail_refresh_with("invalid_grant")
            try:
                for row in rows:
                    oauth.forget_access(row.id)
                    try:
                        oauth.access_token(session, row, provider=fake, cipher=wiring.cipher,
                                           on_reconnect_needed=hook)
                    except oauth.ReconnectRequired:
                        pass
            finally:
                fake.fail_refresh_with(None)
            return status_json(status_of(session, user_id, provider))
