"""The Origin rule for every cookie-delivery state-changing POST (§3.8 H)."""

from __future__ import annotations

from fastapi import Request

from .errors import http_error
from .settings import SignInSettings, origin_of


def request_origin(request: Request) -> str | None:
    """``Origin``, else the origin of ``Referer``. ``Origin: null`` and a missing header give None."""
    origin = request.headers.get("origin")
    if origin is not None:
        return origin_of(origin) if origin.strip().lower() != "null" else None
    referer = request.headers.get("referer")
    return origin_of(referer) if referer else None


def origin_ok(request: Request, settings: SignInSettings) -> bool:
    origin = request_origin(request)
    return origin is not None and origin in settings.allowed_origins


def require_origin(request: Request, settings: SignInSettings) -> None:
    """Raise 403 ``invalid_origin`` unless the origin is the API's own or in ``redirect_allowlist``."""
    if not origin_ok(request, settings):
        raise http_error("invalid_origin")


def has_bearer(request: Request) -> bool:
    scheme, _, rest = request.headers.get("authorization", "").strip().partition(" ")
    return scheme.lower() == "bearer" and bool(rest.strip())
