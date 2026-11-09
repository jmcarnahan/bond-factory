"""Shared plumbing of the route modules: the dependency bundle, JSON reading, redirects, cookie names."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from fastapi.responses import RedirectResponse

from .errors import http_error
from .finish import CookiePolicy
from .policy import ScopePolicy
from .protocols import HandoffStore, IdentityFlow, SessionIssuer, UserDirectory, UserRef
from .settings import SignInSettings

NONCE_PATH = "/auth/signin"
NONCE_MAX_AGE = 600


@dataclass
class Deps:
    directory: UserDirectory
    flow: IdentityFlow
    handoffs: HandoffStore
    sessions: SessionIssuer
    policy: ScopePolicy
    settings: SignInSettings
    cookies: CookiePolicy
    session_dep: Callable[[Request], UserRef | None]
    client_ip: Callable[[Request], str | None]
    scope: Callable[[], AbstractContextManager[Any]]
    connection_model: Any = None
    rate_limit: Callable[[Request, str], None] | None = None
    legacy_refresh: Callable[[Request, dict], Any] | None = None
    providers_payload: Callable[[], dict] | None = None
    labels: Mapping[str, str] = field(default_factory=dict)
    clock: Callable[[], float] | None = None

    def now(self) -> float | None:
        """The injected clock's epoch seconds, or None so the sibling libs use their own real clock."""
        return self.clock() if self.clock is not None else None

    def now_dt(self) -> datetime | None:
        moment = self.now()
        return None if moment is None else datetime.fromtimestamp(moment, UTC)

    def limit(self, request: Request, key: str) -> None:
        if self.rate_limit is not None:
            self.rate_limit(request, key)

    def require_provider(self, provider: str) -> None:
        if provider not in self.settings.providers:
            raise http_error("not_found")

    def nonce_cookie(self, nonce: str) -> str:
        """``bond_signin_<first 8 hex of sha256(nonce)>``: one cookie per flow, so two tabs never collide."""
        return f"{self.settings.nonce_cookie_name}_{hashlib.sha256(nonce.encode()).hexdigest()[:8]}"


async def read_json(request: Request, *, strict: bool = True) -> dict:
    """The JSON object body. Empty gives ``{}``. Anything else that is not an object: 400 (strict) or ``{}``."""
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if isinstance(body, dict):
        return body
    if strict:
        raise http_error("invalid_request")
    return {}


def with_params(target: str, **params: str | None) -> str:
    """``target`` with the non-None ``params`` appended to its query; a fragment is dropped."""
    parts = urlsplit(target)
    query = urlencode([*parse_qsl(parts.query), *((k, v) for k, v in params.items() if v is not None)])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def redirect(target: str, **params: str | None) -> RedirectResponse:
    return RedirectResponse(with_params(target, **params), status_code=302, headers={"Cache-Control": "no-store"})
