"""COPY AS IS (names aside), except the lines marked FAKE MODE ONLY (delete them) or APP REPLACES. Direct sign-in,
mounted: everything an app writes around `bond_signin`, in one place. Read top to bottom.

An app replaces: `directory.py` (its users table), `scope_policy.py` (its roles and scopes) and the settings
names. The rest of this file is the same in every app: build the three library objects, the cookie policy and
the settings, then one `include_router`.
"""

from __future__ import annotations

from dataclasses import dataclass

import bond_signin
from bond_auth_py import (
    SessionStore,
    cookie_name,
    providers_payload,
    refresh_cookie_name,
    refresh_cookie_params,
    session_cookie_params,
)
from bond_oauth import HandoffStore, SignInFlow
from bond_service_kit import ApiError, well_known_router
from fastapi import FastAPI, Request

from . import signin_prune
from .auth_dep import current_user
from .break_glass import (
    legacy_refresh,  # APP REPLACES or deletes (with break_glass.py and the legacy_refresh= argument)
)
from .db import session_scope
from .directory import Directory
from .models.auth import User
from .models.handoffs import OAuthHandoff
from .models.sessions import AuthSession
from .oauth_wiring import OAuthWiring
from .settings import Settings
from .wiring import APP_NAME, client_ip


@dataclass
class SignIn:
    """Everything the routes need, kept on `app.state.signin` (routes/auth.py and routes/connections.py read it)."""

    settings: bond_signin.SignInSettings
    directory: Directory
    flow: SignInFlow
    handoffs: HandoffStore
    sessions: SessionStore
    cookies: bond_signin.CookiePolicy
    policy: bond_signin.ScopePolicy


def check_providers(settings: Settings, wiring: OAuthWiring) -> None:
    """Startup refusals. A fake provider outside fake mode would let anyone sign in as anyone (the `fake*` check is
    FAKE MODE ONLY: an app with no fake providers drops it)."""
    for name in settings.signin_providers:
        if settings.mode != "fake" and name.startswith("fake"):
            raise RuntimeError(f"sign-in provider {name!r} is a fake: it needs SDK_EXAMPLE_MODE=fake")
        if name not in wiring.providers:
            raise RuntimeError(f"sign-in provider {name!r} is not configured (client id and secret missing)")


def signin_settings(settings: Settings) -> bond_signin.SignInSettings:
    fake = settings.mode == "fake"
    return bond_signin.SignInSettings(
        providers=settings.signin_providers, public_base=settings.public_base, prefix=settings.signin_prefix,
        redirect_allowlist=settings.redirect_allowlist, native_return_base=settings.native_return_base,
        native_schemes=settings.native_schemes, break_glass=settings.breakglass,
        cookie_secure=not fake, allow_http=fake)  # FAKE MODE ONLY: an app passes cookie_secure=True, no allow_http


def build_signin(app: FastAPI, wiring: OAuthWiring) -> SignIn:
    settings: Settings = app.state.settings
    auth = app.state.auth_settings
    check_providers(settings, wiring)
    names = settings.signin_providers
    flow = SignInFlow(providers={n: wiring.providers[n] for n in names}, cipher=wiring.cipher,
                      client_ids={n: wiring.client_ids[n] for n in names}, public_base=settings.public_base,
                      pinned_tenants={n: wiring.pinned_tenants[n] for n in names if n in wiring.pinned_tenants})
    cookies = bond_signin.CookiePolicy(
        cookie_name(APP_NAME), refresh_cookie_name(APP_NAME),
        lambda secure: session_cookie_params(auth, secure=secure, ttl_minutes=auth.session_access_ttl_minutes),
        lambda secure: refresh_cookie_params(auth, secure))
    return SignIn(settings=signin_settings(settings), directory=Directory(wiring, fake=settings.mode == "fake"),  # FAKE MODE ONLY: `fake=`
                  flow=flow, handoffs=HandoffStore(OAuthHandoff, wiring.cipher),
                  sessions=SessionStore(AuthSession, auth), cookies=cookies, policy=wiring.policy)


def optional_user(request: Request) -> User | None:
    """The signed-in user, or None (the router decides what a missing session means)."""
    try:
        return current_user(request)
    except ApiError:
        return None


def connection_model(settings: Settings):
    """Where a sign-in that carries mail scopes (Microsoft) keeps its connection; None for sign-in only."""
    if not settings.connections:
        return None
    from .models.connections import OAuthConnection  # an app without connections has no such model

    return OAuthConnection


def label(name: str) -> str:
    return name.replace("-", " ").title()


def install_signin(app: FastAPI, wiring: OAuthWiring) -> SignIn:
    """Mount `/auth/signin/*`, `/auth/refresh`, `/auth/logout`, `/auth/sessions/revoke-all`, `/auth/providers`,
    `/app/return/{provider}` and the two `/.well-known/*` files."""
    settings: Settings = app.state.settings
    assert hasattr(app.state, "oauth"), "build the providers first: providers_wiring.ensure_wiring(app)"
    stack = build_signin(app, wiring)
    app.state.signin = stack
    signin_prune.install(app)  # the daily housekeeping job (see signin_prune.py)

    def payload() -> dict:
        return providers_payload(
            app.state.auth_settings, sync_url=settings.sync_url or None, mock=True if settings.mode == "fake" else None,  # FAKE MODE ONLY: an app omits `mock=`
            signin=[{"id": n, "label": label(n)} for n in settings.signin_providers],
            break_glass=settings.breakglass, default_flow="signin" if settings.signin_providers else "firebase")

    app.include_router(bond_signin.make_signin_router(
        directory=stack.directory, flow=stack.flow, handoffs=stack.handoffs, sessions=stack.sessions,
        policy=stack.policy, settings=stack.settings, cookies=stack.cookies, session_dep=optional_user,
        client_ip=client_ip, session_scope=lambda: session_scope(app.state.session_factory),
        connection_model=connection_model(settings),
        rate_limit=lambda request, key: app.state.limiters["auth"].check(f"{key}:{client_ip(request)}"),
        legacy_refresh=legacy_refresh, include_providers=True, providers_payload=payload,
        labels={n: label(n) for n in settings.signin_providers}))
    # The files iOS and Android read to hand `https://<api>/app/return/<provider>` to the installed app.
    # Values come from the environment; empty lists answer 404.
    # The return page is served under the sign-in prefix's parent; the files name the same path.
    app.include_router(well_known_router(apple_app_ids=settings.apple_app_ids, android_apps=settings.android_apps,
                                         return_path_prefix=stack.settings.return_path_prefix))
    return stack
