"""COPY AS IS. Small pieces of the connect routes: redirect checks, the status JSON, which scopes to ask, who the account is.

`routes/connections.py` is the flow; this file is the part an app copies mostly unchanged.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import bond_oauth as oauth
import bond_signin
from bond_service_kit import ApiError
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .models.auth import User
from .models.connections import OAuthConnection
from .oauth_wiring import OAuthWiring
from .settings import Settings

NONCE_COOKIE = "sdk_example_oauth_nonce"
COOKIE_PATH = "/connections"


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc or "\\" in url:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def redirect_allowed(url: str, settings: Settings) -> bool:
    origin = _origin(url)
    return origin is not None and origin in {_origin(a) for a in settings.redirect_allowlist}


def native_redirect_allowed(url: str, settings: Settings, sign: bond_signin.SignInSettings, provider: str) -> bool:
    """A phone app's return address, the SAME two forms sign-in accepts: the https app link
    `<native_return_base>/<provider>`, or a configured reverse-domain scheme. SDK_EXAMPLE_NATIVE_REDIRECTS (exact
    entries, query ignored) stays as a deprecated alias for the older `sdkdemo://connections` address."""
    if url == f"{sign.native_return_base}/{provider}" or sign.native_scheme_ok(url):
        return True
    parts = urlsplit(url)
    if not parts.scheme or "\\" in url:
        return False
    bare = urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")).lower()
    return bare in {urlunsplit(urlsplit(e)[:3] + ("", "")).lower() for e in settings.native_redirects}


def connect_target(settings: Settings, sign: bond_signin.SignInSettings, provider: str, mode: str,
                   redirect_to: str | None) -> str:
    """Where the flow returns: validated against the web allowlist, or the native one. Raises 400."""
    if mode not in ("", "native", "web"):
        raise ApiError("invalid_mode", "mode must be web or native.", status=400)
    native = mode == "native"
    if native:
        target = redirect_to or (settings.native_redirects[0] if settings.native_redirects else "")
        ok = bool(target) and native_redirect_allowed(target, settings, sign, provider)
    else:
        target = redirect_to or (f"{settings.redirect_allowlist[0].rstrip('/')}/connections"
                                 if settings.redirect_allowlist else "")
        ok = bool(target) and redirect_allowed(target, settings)
    if not ok:
        raise ApiError("redirect_not_allowed", "That redirect address is not allowed.", status=400)
    return target


def status_json(st: oauth.ConnectionStatus) -> dict:
    return {"provider": st.provider, "connected": st.connected, "email": st.email,
            "connected_at": st.connected_at.isoformat() + "Z" if st.connected_at else None,
            "needs_reconnect": st.needs_reconnect, "scopes": st.scopes}


def redirect(target: str, **params: str | None) -> RedirectResponse:
    parts = urlsplit(target)
    query = urlencode([*parse_qsl(parts.query), *((k, v) for k, v in params.items() if v is not None)])
    return RedirectResponse(urlunsplit((parts.scheme, parts.netloc, parts.path, query, "")), status_code=302)


def status_of(session: Session, user_id: str, provider: str) -> oauth.ConnectionStatus:
    return oauth.status(session, user_id=user_id, provider=provider, connection_model=OAuthConnection)


def asked_providers(wiring: OAuthWiring, user: User) -> list[str]:
    """Where this person is asked for more. THE RULE: a user bound to a provider (signed in with it) is asked only
    there, because the ask binds to that account; a user with no bound identity (demo or break-glass sign-in) is
    asked at EVERY provider."""
    bound = user.identity[0] if user.identity else None
    return [name for name in wiring.providers if bound in (None, name)]


def wanted_for(wiring: OAuthWiring, session: Session, user: User) -> list[dict]:
    """The sets the user's role wants, per provider, with `granted` read from the live connection's scopes.
    Computed on every read from the CURRENT capabilities, so a promotion shows the ask on the next load."""
    out: list[dict] = []
    for name in asked_providers(wiring, user):
        granted = status_of(session, user.id, name).scopes
        out += bond_signin.wanted_sets(wiring.policy, user.capabilities or [], name, granted)
    return out


def check_set(wiring: OAuthWiring, user: User, provider: str, set_id: str | None) -> str | None:
    """`?set=` must be one of the sets this user's role wants at this provider: else 400 `invalid_request`."""
    if set_id is None:
        return None
    wants = wiring.policy.wanted(user.capabilities or [], provider) if provider in asked_providers(wiring, user) else []
    if set_id not in {s.id for s in wants}:
        raise ApiError("invalid_request", "That scope set is not available to this account.", status=400)
    return set_id


def scopes_for(wiring: OAuthWiring, settings: Settings, session: Session, user: User, provider: str,
               set_id: str | None) -> list[str]:
    """The scopes a connect asks for, from the POLICY (never a library default). With a set: that set (Microsoft:
    plus what is granted, since it has no server-side merge). Without: every set the role wants, else sign-in's."""
    granted = status_of(session, user.id, provider).scopes
    policy = wiring.policy
    if set_id:
        scopes = bond_signin.connect_scopes(policy, set_id, granted)
    else:
        sets = policy.wanted(user.capabilities or [], provider)
        scopes = list(dict.fromkeys(s for item in sets for s in item.scopes)) or list(policy.signin_scopes(provider))
    if settings.mode == "fake":  # the fake does not merge earlier grants the way Google's include_granted_scopes does
        scopes = list(dict.fromkeys([*granted, *scopes]))
    return scopes


def account_binding(wiring: OAuthWiring, user: User, provider: str) -> tuple[str | None, str | None]:
    """`(login_hint, expected_subject)`: the connect must use the account the person signed in with. A user with
    no bound identity for this provider (a break-glass row) binds nothing. A shared mailbox connect (an app's
    office address) would skip this; the example has none."""
    identity = user.identity
    if identity is None:
        return None, None
    if identity[0] != provider:
        # Signed in with one provider, connecting another: nothing ties that account to this person. Allowed only
        # where the policy itself asks for something at that provider (a shared-mailbox connect is the other
        # exception an app adds, with `shared=True`).
        if not any(s.provider == provider for sets in wiring.policy.by_capability.values() for s in sets):
            raise ApiError("invalid_request", "Connect uses your sign-in account.", status=400)
        return None, None
    return user.email, identity[1]


def set_declined(wiring: OAuthWiring, set_id: str | None, scopes: str | None) -> bool:
    """True when the person finished the consent but left the asked set out of the grant."""
    if not set_id:
        return False
    return bool(oauth.scope_drift(scopes or "", wiring.policy.set(set_id).scopes))


def provider_or_404(wiring: OAuthWiring, name: str) -> oauth.OAuthProvider:
    provider = wiring.providers.get(name)
    if provider is None:
        raise ApiError("unknown_provider", "That provider is not configured here.", status=404)
    return provider


def reason_of(error: str) -> str:
    """The provider's refusal as the shared code: a person who pressed Deny has `consent_declined`."""
    return "consent_declined" if error == "access_denied" else error[:64]
