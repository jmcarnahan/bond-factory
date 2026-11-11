"""Bearer-token auth that fails closed (plan D5)."""

from __future__ import annotations

import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

from .errors import error_body

MIN_TOKEN_CHARS = 32
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
OPEN_PATHS = frozenset({"/healthz"})


class AuthConfigError(RuntimeError):
    """The process must not start with this configuration."""


def require_token(env: dict[str, str] | None = None) -> str | None:
    """Return the token to enforce, or None when auth is off for local dev; raise to refuse to start."""
    env = os.environ if env is None else env
    if env.get("ROOF_MEASURE_AUTH", "on").lower() == "off":
        host = env.get("ROOF_MEASURE_HOST", "::")
        if host not in LOOPBACK_HOSTS:
            raise AuthConfigError("ROOF_MEASURE_AUTH=off needs ROOF_MEASURE_HOST set to 127.0.0.1, ::1 or localhost.")
        return None
    token = env.get("ROOF_MEASURE_TOKEN", "").strip()  # a pasted trailing newline must not mean permanent 401s
    if len(token) < MIN_TOKEN_CHARS:
        raise AuthConfigError(f"ROOF_MEASURE_TOKEN must be set and at least {MIN_TOKEN_CHARS} characters.")
    if not token.isascii():
        raise AuthConfigError("ROOF_MEASURE_TOKEN must be ASCII: HTTP headers are decoded as latin-1.")
    return token


def unauthorized() -> JSONResponse:
    return JSONResponse(error_body("unauthorized"), status_code=401, headers={"WWW-Authenticate": "Bearer"})


def token_ok(header: str | None, token: str) -> bool:
    scheme, _, value = (header or "").partition(" ")
    if scheme.lower() != "bearer" or not value:
        return False
    return hmac.compare_digest(value.strip().encode(), token.encode())


def install(app, token: str | None) -> None:
    """Middleware: every path but the open ones needs the bearer token (CORS preflights pass through)."""

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        if token is None or request.url.path in OPEN_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        if not token_ok(request.headers.get("authorization"), token):
            return unauthorized()
        return await call_next(request)
