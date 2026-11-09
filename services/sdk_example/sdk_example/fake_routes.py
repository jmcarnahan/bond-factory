"""REPLACE (an app deletes it). Fake mode only: the consent page, and `simulate-reuse` (no connections code: sign-in needs them).

Real mode never registers these. The page stands in for the provider's own consent screen, so a person can sign in
as any seeded identity, as one nobody invited, or as a typed address, and can leave a scope set unticked.

Element ids (the demo and the UI walk rely on them): `sdk-consent-identity` (select), `sdk-consent-email` (free
text, wins when filled), `sdk-consent-set-<id>` (one box per asked set), `sdk-consent-allow`, `sdk-consent-deny`.
"""

from __future__ import annotations

import html
from datetime import timedelta
from urllib.parse import urlencode

import bond_oauth as oauth
import bond_signin
from bond_auth_py import AuthRefused
from bond_oauth.fake import mock_code
from bond_service_kit import ApiError
from bond_signin import ScopeSet
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import update

from .auth_dep import UsersRevocation, auth_settings, invalid_token
from .db import session_scope
from .models.auth import DEMO_USERS, UNINVITED_EMAIL, User, utcnow
from .models.sessions import AuthSession
from .oauth_wiring import OAuthWiring
from .scope_policy import FAKE_GOOGLE, FAKE_MICROSOFT

# PICK: who the consent page preselects (a person you can sign in as). oauth_wiring.DEFAULT_EMAIL is different: the
# identity the bare code `mock` stands for, which older tests still use.
PICK = {FAKE_GOOGLE: "demo@example.com", FAKE_MICROSOFT: "demo.microsoft@example.com"}  # preselected identity
PAGE = (
    "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>Fake consent</title><body style='font-family:sans-serif;max-width:28rem;margin:3rem auto;padding:0 1rem'>"
    "<h1>Allow access?</h1><p>This is the fake {provider} consent page. Nothing leaves this machine.</p>"
    "<form method=get action='/connections/fake/consent/submit'>"
    "<input type=hidden name=state value='{state}'><input type=hidden name=shown value='{shown}'>"
    "<p><label>Sign in as<br><select id=sdk-consent-identity name=identity>{options}</select></label></p>"
    "<p><label>or type an address<br><input id=sdk-consent-email name=email type=text autocomplete=off></label></p>"
    "{boxes}<p><button type=submit id=sdk-consent-allow name=action value=allow>Allow</button> "
    "<button type=submit id=sdk-consent-deny name=action value=deny>Deny</button></p></form></body>"
)


def identity_options(selected: str, esc=html.escape) -> str:
    """The seeded identities, the uninvited one, and (when a hint names someone else) that address."""
    emails = [row["email"] for row in DEMO_USERS] + [UNINVITED_EMAIL]
    if selected not in emails:
        emails.insert(0, selected)
    return "".join(f"<option value='{esc(e)}'{' selected' if e == selected else ''}>{esc(e)}</option>"
                   for e in emails)


def register_fake(app: FastAPI, wiring: OAuthWiring) -> None:

    def sets_asked(payload: oauth.StatePayload) -> list[ScopeSet]:
        """The scope sets this request asks: a sign-in asks none (identity or pre-consented), a connect asks its
        set, or every set of the provider when it names none."""
        if payload.intent != "connect":
            return []
        every = [s for sets in wiring.policy.by_capability.values() for s in sets if s.provider == payload.provider]
        return [s for s in every if payload.set_id in (None, s.id)]

    @app.get("/connections/fake/consent", response_class=HTMLResponse)
    def fake_consent(state: str = "", hint: str = "") -> HTMLResponse:
        try:
            payload = oauth.decode_state(wiring.cipher, state)
        except oauth.OAuthError as exc:
            raise ApiError(exc.code, str(exc), status=400) from exc
        esc = html.escape
        asked = sets_asked(payload)
        boxes = "".join(
            f"<p><label><input type=checkbox id='sdk-consent-set-{esc(s.id)}' name=set value='{esc(s.id)}' checked> "
            f"{esc(s.label or s.id)}</label></p>" for s in asked)
        default = hint or PICK.get(payload.provider, DEMO_USERS[0]["email"])
        return HTMLResponse(PAGE.format(provider=esc(payload.provider), state=esc(state), options=identity_options(default),
                                        shown=esc(",".join(s.id for s in asked)), boxes=boxes))

    @app.get("/connections/fake/consent/submit")
    def submit(request: Request) -> RedirectResponse:
        """What the provider does after the consent screen: back to the app's callback with a code or an error."""
        q = request.query_params
        state = q.get("state", "")
        try:
            payload = oauth.decode_state(wiring.cipher, state)
        except oauth.OAuthError as exc:
            raise ApiError(exc.code, str(exc), status=400) from exc
        path = (f"{request.app.state.signin.settings.prefix}/signin/{payload.provider}/callback" if payload.intent == "signin"
                else f"/connections/{payload.provider}/callback")
        if q.get("action") == "deny":
            return RedirectResponse(f"{path}?{urlencode({'state': state, 'error': 'access_denied'})}", status_code=302)
        email = (q.get("email") or q.get("identity") or "").strip().lower()
        ticked = set(q.getlist("set"))
        declined = [i for i in q.get("shown", "").split(",") if i and i not in ticked]
        code = mock_code(email, declined)
        return RedirectResponse(f"{path}?{urlencode({'state': state, 'code': code})}", status_code=302)

    @app.post("/auth/simulate-reuse")
    def simulate_reuse_route(request: Request) -> Response:
        """The demo's `sdk.auth.simulate-reuse` button: replay an old refresh token and get signed out."""
        stack = request.app.state.signin
        bond_signin.require_origin(request, stack.settings)
        token = request.cookies.get(stack.cookies.refresh_name)
        if not token:
            raise invalid_token("Sign in to continue.")
        return simulate_reuse(request, token)


def simulate_reuse(request: Request, token: str) -> Response:
    """Rotate the token, age the parent past the replay grace, then replay the parent: what a thief holding an old
    token does. The library's reuse path revokes the family; we answer what a real refresh would (401
    refresh_reused, cookies cleared)."""
    stack, auth = request.app.state.signin, auth_settings(request)
    code: str | None = None
    with session_scope(request.app.state.session_factory) as session:
        def loader(user_id: str):
            user = session.get(User, user_id)
            return stack.directory.session_spec(session, user) if user and user.is_active else None

        revocation = UsersRevocation(session)
        try:
            child = stack.sessions.rotate(session, refresh_token=token, rotation_id=None, loader=loader,
                                          revocation=revocation)
            aged = utcnow() - timedelta(seconds=auth.refresh_reuse_grace_seconds + 60)
            session.execute(update(AuthSession).where(AuthSession.family_id == child.family_id,
                                                      AuthSession.rotated_at.is_not(None)).values(rotated_at=aged))
            session.flush()
            stack.sessions.rotate(session, refresh_token=token, rotation_id=None, loader=loader,
                                  revocation=revocation)
        except AuthRefused as exc:  # the replay: ReuseDetected, its family revoke already committed by the lib
            code = exc.code
    if code is None:
        raise ApiError("simulation_failed", "The replay was not refused.", status=500)
    reply = JSONResponse({"detail": {"code": code, "message": bond_signin.MESSAGES[code]}},
                         status_code=bond_signin.STATUS_FOR_CODE[code], headers={"Cache-Control": "no-store"})
    bond_signin.clear_session_cookies(reply, settings=stack.settings, cookies=stack.cookies)
    return reply
