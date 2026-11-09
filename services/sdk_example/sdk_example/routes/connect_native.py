"""COPY AS IS (drop it if the app has no phone client). The phone-app connect flow: the system browser finishes
consent with no cookie, the result waits in `oauth_handoffs`, and the app redeems it with its bearer token AND the
device secret whose sha256 it sent at start. Nothing is stored until redeem, and redeem needs the bearer of the
user who started the flow, so tokens never land under another user's row. That guarantee depends on the
`expected_subject` binding: the consent must be by the account the person signed in with, which is why a native
start is refused for a user with no bound identity.

`register` (auto-discovered) adds the redeem route; `check_start` and `native_callback` are called from
`connections.py`. They read `app.state.oauth` and `app.state.signin` at request time (built by later modules).
"""

from __future__ import annotations

import re

import bond_oauth as oauth
from bond_auth_py import has
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .. import connect_helpers as helpers
from ..auth_dep import require_capability
from ..db import session_scope
from ..models.auth import User, utcnow
from ..models.connections import OAuthConnection
from ..oauth_wiring import callback_url

MANAGE = "connections.manage"
manage = require_capability(MANAGE)
HEX64, ATTEMPT = re.compile(r"^[0-9a-f]{64}$"), re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RedeemBody(BaseModel):
    code: str
    device_secret: str  # the phone's secret; the sha256 of its text was sent at start


def check_start(device_challenge: str | None, attempt: str | None) -> None:
    """A phone start carries the device challenge (sha256 hex) and an attempt id, as sign-in does: else 400."""
    if not (device_challenge and HEX64.match(device_challenge)) or not (attempt and ATTEMPT.match(attempt)):
        raise ApiError("invalid_request", "A phone start needs device_challenge (sha256 hex) and attempt.",
                       status=400)


def native_callback(app: FastAPI, provider: str, payload: oauth.StatePayload, state: str, code: str,
                    error: str) -> RedirectResponse:
    wiring, settings = app.state.oauth, app.state.settings
    target, echo = payload.redirect_to, {"attempt": payload.attempt_id}
    with session_scope(app.state.session_factory) as session:
        owner = session.get(User, payload.sub)
        if owner is None or not has(list(owner.capabilities or []), MANAGE):  # the role may have changed
            return helpers.redirect(target, connection="error", provider=provider, reason="forbidden", **echo)
    if error:
        return helpers.redirect(target, connection="error", provider=provider,
                                reason=helpers.reason_of(error), **echo)
    try:
        with session_scope(app.state.session_factory) as session:
            pending = oauth.complete(session, state=state, code=code, providers=wiring.providers,
                                     cipher=wiring.cipher, connection_model=OAuthConnection,
                                     redirect_uri=callback_url(settings, provider), expected_provider=provider,
                                     expected_user_id=None, expected_nonce=None)
            if helpers.set_declined(wiring, payload.set_id, pending.fields.get("scopes")):
                return helpers.redirect(target, connection="error", provider=provider,
                                        reason="consent_declined", **echo)
            code_out = app.state.signin.handoffs.issue(
                session, purpose="connect", provider=provider, device_hash=payload.device_hash or "",
                attempt_id=payload.attempt_id,
                payload={"user_id": payload.sub, "provider": provider, "owner": pending.owner,
                         "connection_name": pending.connection_name, "fields": pending.fields})
    except oauth.OAuthError as exc:
        return helpers.redirect(target, connection="error", provider=provider, reason=exc.code, **echo)
    except oauth.RetryableError:
        return helpers.redirect(target, connection="error", provider=provider, reason="unavailable", **echo)
    return helpers.redirect(target, connection="connected", provider=provider, code=code_out, **echo)


def register(app: FastAPI) -> None:
    @app.post("/connections/{provider}/redeem")
    def redeem(provider: str, body: RedeemBody, user_id: str = Depends(manage)) -> dict:
        helpers.provider_or_404(app.state.oauth, provider)
        with session_scope(app.state.session_factory) as session:
            try:
                data = app.state.signin.handoffs.redeem(session, code=body.code, device_secret=body.device_secret,
                                                        purpose="connect")
                if data.get("user_id") != user_id or data.get("provider") != provider:  # the code is spent either way
                    raise oauth.OAuthError("invalid_handoff", "The hand-off code is not valid")
            except oauth.OAuthError as exc:
                raise ApiError(exc.code, str(exc), status=400) from exc
            oauth.store_connection(session, OAuthConnection, owner=data["owner"], provider=provider,
                                   connection_name=data["connection_name"], fields=data["fields"], stamp=utcnow())
            return helpers.status_json(helpers.status_of(session, user_id, provider))
