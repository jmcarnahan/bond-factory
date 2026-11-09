"""COPY AS IS. Web connect: list (with the wanted scope sets), start, go, callback, disconnect.

The fake-mode consent page and the expiry switch live in `fake_routes.py`. Sign-in is the library's
(`signin_wiring.py`); this is the ROLE ASK: after sign-in, a person whose role needs mail or calendar connects it
through `start?set=<id>`, bound to the account they signed in with.
"""

from __future__ import annotations

import hmac
import logging
from urllib.parse import quote

import bond_oauth as oauth
from bond_auth_py import has
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from .. import connect_helpers as helpers
from ..auth_dep import current_user, current_user_id, require_capability
from ..db import session_scope
from ..fake_routes import register_fake
from ..models.auth import User, utcnow
from ..models.connections import OAuthConnection
from ..oauth_wiring import OAuthWiring, build_wiring, callback_url
from ..settings import Settings
from .connect_native import check_start, native_callback

LOGGER = logging.getLogger("sdk_example.connections")
manage = require_capability("connections.manage")  # start, redeem, disconnect; listing needs a session only
MANAGE = "connections.manage"


def _clear_nonce(reply):
    reply.delete_cookie(helpers.NONCE_COOKIE, path=helpers.COOKIE_PATH)
    return reply


def _hook(connection: OAuthConnection, reason: str) -> None:
    LOGGER.warning("connection %s needs reconnect (%s)", connection.id, reason)


def register(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    wiring: OAuthWiring = build_wiring(settings)
    app.state.oauth = wiring
    factory = app.state.session_factory

    def provider_or_404(name: str) -> oauth.OAuthProvider:
        return helpers.provider_or_404(wiring, name)

    def redirect_uri(provider: str) -> str:
        return callback_url(settings, provider)

    @app.get("/connections")
    def list_connections(request: Request) -> dict:
        user = current_user(request)
        with session_scope(factory) as session:
            return {"connections": [helpers.status_json(helpers.status_of(session, user.id, n))
                                    for n in wiring.providers],
                    "wanted": helpers.wanted_for(wiring, session, user)}

    @app.get("/connections/{provider}/start")
    def start(provider: str, request: Request, redirect_to: str | None = None, mode: str = "",
              set: str | None = None, device_challenge: str | None = None, attempt: str | None = None,
              user_id: str = Depends(manage)) -> dict:
        provider_or_404(provider)
        target = helpers.connect_target(settings, app.state.signin.settings, provider, mode, redirect_to)
        user = current_user(request)
        set_id = helpers.check_set(wiring, user, provider, set)
        hint, subject = helpers.account_binding(wiring, user, provider)
        if mode == "native" and subject is None:  # the hand-off guarantee rests on this binding (see connect_native.py)
            raise ApiError("invalid_request", "A phone connect needs an account bound by sign-in.", status=400)
        with session_scope(factory) as session:
            if mode == "native":
                check_start(device_challenge, attempt)
            scopes = helpers.scopes_for(wiring, settings, session, user, provider, set_id)
            native = mode == "native"
            state = oauth.start_flow(session, user_id=user_id, provider_name=provider,
                                     provider=provider_or_404(provider), scopes=scopes, redirect_to=target,
                                     cipher=wiring.cipher, redirect_uri=redirect_uri(provider), set_id=set_id,
                                     login_hint=hint, expected_subject=subject, native=native,
                                     device_hash=device_challenge if native else None,
                                     attempt_id=attempt if native else None).state
        # The browser goes to /go first so the nonce cookie is set in the browser that finishes the flow
        # (a native flow has no cookie: the app opens this URL in the system browser).
        return {"url": f"{settings.public_base}/connections/{provider}/go?state={quote(state, safe='')}"}

    def read_state(provider: str, state: str) -> oauth.StatePayload:
        try:
            payload = oauth.decode_state(wiring.cipher, state)
        except oauth.OAuthError as exc:  # no trustworthy redirect target exists
            raise ApiError(exc.code, str(exc), status=400) from exc
        if payload.intent != "connect":
            raise ApiError("invalid_state", "That link is not for a connection.", status=400)
        if payload.provider != provider:
            raise ApiError("provider_mismatch", "The sign-in belongs to another provider.", status=400)
        if payload.native:
            ok = helpers.native_redirect_allowed(payload.redirect_to, settings, app.state.signin.settings, provider)
        else:
            ok = helpers.redirect_allowed(payload.redirect_to, settings)
        if not ok:
            raise ApiError("redirect_not_allowed", "That redirect address is not allowed.", status=400)
        return payload

    @app.get("/connections/{provider}/go")
    def go(provider: str, request: Request, state: str = "") -> RedirectResponse:
        """Top-level navigation that needs the session cookie: the state must belong to the signed-in person.
        A native state (phone app, system browser) needs no session and sets no cookie.

        That is what binds the flow to this browser. An attacker's /go link, opened by a victim, carries the attacker's
        state and is refused (403) before any nonce cookie is set.
        """
        impl = provider_or_404(provider)
        payload = read_state(provider, state)
        if not payload.native and payload.sub != current_user_id(request):
            raise ApiError("forbidden", "This sign-in link was started by someone else.", status=403)
        with session_scope(factory) as session:  # the state names the user; scopes are recomputed, not carried
            owner = session.get(User, payload.sub)
            if owner is None or not has(list(owner.capabilities or []), "connections.manage"):
                raise ApiError("forbidden", "This needs the connections.manage capability.", status=403)
            scopes = helpers.scopes_for(wiring, settings, session, owner, provider, payload.set_id)
        url = impl.authorize_url(state=state, challenge=oauth.pkce.challenge(payload.verifier), scopes=scopes,
                                 redirect_uri=redirect_uri(provider), login_hint=payload.login_hint)
        reply = RedirectResponse(settings.public_base + url if url.startswith("/") else url, status_code=302)
        if payload.native:  # the system browser has no session; the encrypted state is the only credential
            return reply
        reply.set_cookie(helpers.NONCE_COOKIE, payload.nonce, max_age=600, httponly=True, samesite="lax",
                         path=helpers.COOKIE_PATH, secure=settings.mode != "fake")
        return reply

    @app.get("/connections/{provider}/callback")
    def callback(provider: str, request: Request, state: str = "", code: str = "", error: str = ""):
        """Needs the session cookie AND the nonce cookie, both set in the browser that started the flow.
        A native state completes without either, stores nothing and redirects to the app with a one-time hand-off code."""
        payload = read_state(provider, state)
        if payload.native:
            return native_callback(app, provider, payload, state, code, error)
        user_id = current_user_id(request)
        nonce = request.cookies.get(helpers.NONCE_COOKIE, "")
        if (payload.sub != user_id or not nonce
                or not hmac.compare_digest(nonce.encode(), payload.nonce.encode())):
            # Not the person or browser that started the flow: the redirect target comes from an untrusted link.
            return _clear_nonce(JSONResponse(status_code=400, content={"detail": {
                "code": "invalid_state", "message": "The sign-in was not started in this browser. Start again."}}))
        target = payload.redirect_to
        if not has(list(current_user(request).capabilities or []), MANAGE):  # the role may have changed since start
            return _clear_nonce(helpers.redirect(target, connection="error", provider=provider, reason="forbidden"))
        if error:
            return _clear_nonce(helpers.redirect(target, connection="error", provider=provider,
                                                 reason=helpers.reason_of(error)))
        try:
            with session_scope(factory) as session:
                prior = [r.id for r in session.query(OAuthConnection).filter_by(
                    user_id=user_id, provider=provider, revoked_at=None)]
                row = oauth.complete(session, state=state, code=code, providers=wiring.providers,
                                     cipher=wiring.cipher, connection_model=OAuthConnection,
                                     redirect_uri=redirect_uri(provider), expected_provider=provider,
                                     expected_user_id=user_id, expected_nonce=nonce)
                declined = helpers.set_declined(wiring, payload.set_id, row.scopes)
                if declined:  # complete stores first, so undo: drop the new row, bring the old grant back
                    row.revoked_at = utcnow()
                    session.flush()  # free the partial unique index (one live row per owner/provider/name) first
                    oauth.forget_access(row.id)
                    for old in session.query(OAuthConnection).filter(OAuthConnection.id.in_(prior)):
                        old.revoked_at = None
        except oauth.OAuthError as exc:
            return _clear_nonce(helpers.redirect(target, connection="error", provider=provider, reason=exc.code))
        except oauth.RetryableError:
            return _clear_nonce(helpers.redirect(target, connection="error", provider=provider,
                                                 reason="unavailable"))
        if declined:  # consented, but without the set that was asked: it stays wanted
            return _clear_nonce(helpers.redirect(target, connection="error", provider=provider,
                                                 reason="consent_declined"))
        return _clear_nonce(helpers.redirect(target, connection="connected", provider=provider))

    @app.delete("/connections/{provider}")
    def disconnect(provider: str, user_id: str = Depends(manage)) -> dict:
        impl = provider_or_404(provider)
        with session_scope(factory) as session:
            oauth.disconnect(session, user_id=user_id, provider_name=provider, connection_model=OAuthConnection,
                             provider=impl, cipher=wiring.cipher)
            return helpers.status_json(helpers.status_of(session, user_id, provider))

    if settings.mode == "fake":
        register_fake(app, wiring, provider_or_404, manage, _hook)
