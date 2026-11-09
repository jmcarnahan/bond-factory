"""``make_signin_router``: the whole sign-in surface behind one call."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import Any

from fastapi import APIRouter, Request

from . import return_page, routes_native, routes_providers, routes_session, routes_web
from ._common import Deps
from .finish import CookiePolicy
from .policy import ScopePolicy
from .protocols import HandoffStore, IdentityFlow, SessionIssuer, UserDirectory, UserRef
from .settings import SignInSettings


def make_signin_router(*, directory: UserDirectory, flow: IdentityFlow, handoffs: HandoffStore,
                       sessions: SessionIssuer, policy: ScopePolicy, settings: SignInSettings,
                       cookies: CookiePolicy, session_dep: Callable[[Request], UserRef | None],
                       client_ip: Callable[[Request], str | None],
                       session_scope: Callable[[], AbstractContextManager[Any]],
                       connection_model: Any = None, rate_limit: Callable[[Request, str], None] | None = None,
                       legacy_refresh: Callable[[Request, dict], Any] | None = None,
                       include_providers: bool = False, providers_payload: Callable[[], dict] | None = None,
                       labels: Mapping[str, str] | None = None,
                       clock: Callable[[], float] | None = None) -> APIRouter:
    """Mount with ``app.include_router``. ``session_scope()`` opens the DB transaction (commit on exit,
    rollback on an exception). ``rate_limit(request, key)`` is called with ``signin_start``, ``signin_callback``,
    ``redeem`` or ``refresh`` before any work. ``legacy_refresh(request, body)`` handles ``{id_token}`` bodies. ``clock()`` (epoch seconds) is passed as ``now``
    to the sessions, hand-off and order calls; None leaves each lib on its own clock."""
    deps = Deps(directory=directory, flow=flow, handoffs=handoffs, sessions=sessions, policy=policy,
                settings=settings, cookies=cookies, session_dep=session_dep, client_ip=client_ip,
                scope=session_scope, connection_model=connection_model, rate_limit=rate_limit,
                legacy_refresh=legacy_refresh, providers_payload=providers_payload, labels=labels or {}, clock=clock)
    router = APIRouter(tags=["signin"])
    routes_web.register(router, deps)
    routes_native.register(router, deps)
    routes_session.register(router, deps)
    return_page.register(router)
    if include_providers:
        routes_providers.register(router, deps)
    return router
