"""OAuth connections: list, start, callback, disconnect, and the fake-mode consent page and expiry switch."""

from __future__ import annotations

import hmac
import html
import logging
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import bond_oauth as oauth
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..auth_dep import current_user_id, require_capability
from ..db import session_scope
from ..models.connections import OAuthConnection
from ..oauth_wiring import OAuthWiring, build_wiring, callback_url, public_base
from ..settings import Settings

LOGGER = logging.getLogger("sdk_example.connections")
NONCE_COOKIE = "sdk_example_oauth_nonce"
COOKIE_PATH = "/connections"
manage = require_capability("connections.manage")  # start, disconnect and simulate-expiry; listing needs a session only


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or "\\" in url:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def redirect_allowed(url: str, settings: Settings) -> bool:
    origin = _origin(url)
    return origin is not None and origin in {_origin(a) for a in settings.redirect_allowlist}


def _status_json(st: oauth.ConnectionStatus) -> dict:
    return {"provider": st.provider, "connected": st.connected, "email": st.email,
            "connected_at": st.connected_at.isoformat() + "Z" if st.connected_at else None,
            "needs_reconnect": st.needs_reconnect, "scopes": st.scopes}


def _redirect(target: str, **params: str) -> RedirectResponse:
    parts = urlsplit(target)
    query = urlencode([*parse_qsl(parts.query), *params.items()])
    return RedirectResponse(urlunsplit((parts.scheme, parts.netloc, parts.path, query, "")), status_code=302)


def _clear_nonce(reply):
    reply.delete_cookie(NONCE_COOKIE, path=COOKIE_PATH)
    return reply


def _hook(connection: OAuthConnection, reason: str) -> None:
    LOGGER.warning("connection %s needs reconnect (%s)", connection.id, reason)


def register(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    wiring: OAuthWiring = build_wiring(settings)
    app.state.oauth = wiring

    def provider_or_404(name: str) -> oauth.OAuthProvider:
        provider = wiring.providers.get(name)
        if provider is None:
            raise ApiError("unknown_provider", "That provider is not configured here.", status=404)
        return provider

    def status_of(session, user_id: str, name: str) -> oauth.ConnectionStatus:
        return oauth.status(session, user_id=user_id, provider=name, connection_model=OAuthConnection)

    @app.get("/connections")
    def list_connections(request: Request, user_id: str = Depends(current_user_id)) -> list[dict]:
        with session_scope(request.app.state.session_factory) as session:
            return [_status_json(status_of(session, user_id, name)) for name in wiring.providers]

    @app.get("/connections/{provider}/start")
    def start(provider: str, request: Request, redirect_to: str | None = None,
              user_id: str = Depends(manage)) -> dict:
        impl = provider_or_404(provider)
        if redirect_to:
            target = redirect_to
        elif settings.redirect_allowlist:
            target = f"{settings.redirect_allowlist[0].rstrip('/')}/connections"
        else:
            target = ""
        if not target or not redirect_allowed(target, settings):
            raise ApiError("redirect_not_allowed", "That redirect address is not allowed.", status=400)
        with session_scope(request.app.state.session_factory) as session:
            flow = oauth.start_flow(session, user_id=user_id, provider_name=provider, provider=impl,
                                    scopes=wiring.scopes[provider], redirect_to=target, cipher=wiring.cipher,
                                    redirect_uri=callback_url(request, provider))
        # The browser goes to /go first so the nonce cookie is set in the browser that finishes the flow.
        return {"url": f"{public_base(request)}/connections/{provider}/go?state={quote(flow.state, safe='')}"}

    def read_state(provider: str, state: str) -> oauth.StatePayload:
        try:
            payload = oauth.decode_state(wiring.cipher, state)
        except oauth.OAuthError as exc:  # no trustworthy redirect target exists
            raise ApiError(exc.code, str(exc), status=400) from exc
        if payload.provider != provider:
            raise ApiError("provider_mismatch", "The sign-in belongs to another provider.", status=400)
        if not redirect_allowed(payload.redirect_to, settings):
            raise ApiError("redirect_not_allowed", "That redirect address is not allowed.", status=400)
        return payload

    @app.get("/connections/{provider}/go")
    def go(provider: str, request: Request, state: str = "",
           user_id: str = Depends(current_user_id)) -> RedirectResponse:
        """Top-level navigation that needs the session cookie: the state must belong to the signed-in person.

        That is what binds the flow to this browser. An attacker's /go link, opened by a victim, carries the attacker's
        state and is refused (403) before any nonce cookie is set.
        """
        impl = provider_or_404(provider)
        payload = read_state(provider, state)
        if payload.sub != user_id:
            raise ApiError("forbidden", "This sign-in link was started by someone else.", status=403)
        url = impl.authorize_url(state=state, challenge=oauth.pkce.challenge(payload.verifier),
                                 scopes=wiring.scopes[provider], redirect_uri=callback_url(request, provider))
        reply = RedirectResponse(public_base(request) + url if url.startswith("/") else url, status_code=302)
        reply.set_cookie(NONCE_COOKIE, payload.nonce, max_age=600, httponly=True, samesite="lax",
                         path=COOKIE_PATH, secure=settings.mode != "fake")
        return reply

    @app.get("/connections/{provider}/callback")
    def callback(provider: str, request: Request, state: str = "", code: str = "", error: str = "",
                 user_id: str = Depends(current_user_id)):
        """Needs the session cookie AND the nonce cookie, both set in the browser that started the flow."""
        payload = read_state(provider, state)
        nonce = request.cookies.get(NONCE_COOKIE, "")
        if (payload.sub != user_id or not nonce
                or not hmac.compare_digest(nonce.encode(), payload.nonce.encode())):
            # Not the person or browser that started the flow: the redirect target comes from an untrusted link.
            return _clear_nonce(JSONResponse(status_code=400, content={"detail": {
                "code": "invalid_state", "message": "The sign-in was not started in this browser. Start again."}}))
        if error:
            return _clear_nonce(_redirect(payload.redirect_to, connection="error", provider=provider,
                                          reason=error[:64]))
        try:
            with session_scope(request.app.state.session_factory) as session:
                oauth.complete(session, state=state, code=code, providers=wiring.providers, cipher=wiring.cipher,
                               connection_model=OAuthConnection, redirect_uri=callback_url(request, provider),
                               expected_provider=provider, expected_user_id=user_id, expected_nonce=nonce)
        except oauth.OAuthError as exc:
            return _clear_nonce(_redirect(payload.redirect_to, connection="error", provider=provider, reason=exc.code))
        except oauth.RetryableError:
            return _clear_nonce(_redirect(payload.redirect_to, connection="error", provider=provider,
                                          reason="unavailable"))
        return _clear_nonce(_redirect(payload.redirect_to, connection="connected", provider=provider))

    @app.delete("/connections/{provider}")
    def disconnect(provider: str, request: Request, user_id: str = Depends(manage)) -> dict:
        impl = provider_or_404(provider)
        with session_scope(request.app.state.session_factory) as session:
            oauth.disconnect(session, user_id=user_id, provider_name=provider, connection_model=OAuthConnection,
                             provider=impl, cipher=wiring.cipher)
            return _status_json(status_of(session, user_id, provider))

    if settings.mode != "fake":
        return

    @app.get("/connections/fake/consent", response_class=HTMLResponse)
    def fake_consent(state: str = "") -> HTMLResponse:
        try:
            payload = oauth.decode_state(wiring.cipher, state)
        except oauth.OAuthError as exc:
            raise ApiError(exc.code, str(exc), status=400) from exc
        esc = html.escape
        page = (
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Fake consent</title><body style='font-family:sans-serif;max-width:28rem;margin:3rem auto'>"
            f"<h1>Allow access?</h1><p>This is the fake {esc(payload.provider)} consent page. Nothing leaves this machine.</p>"
            f"<form method=get action='/connections/{esc(payload.provider)}/callback'>"
            f"<input type=hidden name=state value='{esc(state)}'><input type=hidden name=code value=mock>"
            "<button type=submit id=sdk-consent-allow>Allow</button></form></body>"
        )
        return HTMLResponse(page)

    @app.post("/connections/{provider}/simulate-expiry")
    def simulate_expiry(provider: str, request: Request, user_id: str = Depends(manage)) -> dict:
        provider_or_404(provider)
        fake = wiring.fakes[provider]
        with session_scope(request.app.state.session_factory) as session:
            rows = session.query(OAuthConnection).filter_by(user_id=user_id, provider=provider, revoked_at=None).all()
            if not rows:
                raise ApiError("not_connected", "Connect this provider first.", status=404)
            fake.fail_refresh_with("invalid_grant")
            try:
                for row in rows:
                    oauth.forget_access(row.id)
                    try:
                        oauth.access_token(session, row, provider=fake, cipher=wiring.cipher,
                                           on_reconnect_needed=_hook)
                    except oauth.ReconnectRequired:
                        pass
            finally:
                fake.fail_refresh_with(None)
            return _status_json(status_of(session, user_id, provider))
