"""Authentication dependencies every protected route uses.

    @router.get("/things")
    def things(user_id: str = Depends(current_user_id)): ...
    @router.post("/things")
    def make(user_id: str = Depends(require_capability("tasks.write"))): ...

The token is the Authorization bearer first, then the cookie ``sdk_example_access_token``. Authority (active flag,
capabilities, revocation mark) is re-read from the users table on every request, never taken from the token.
"""

from __future__ import annotations

from datetime import datetime

from bond_auth_py import (
    DEACTIVATED,
    INVALID_TOKEN,
    AuthRefused,
    AuthSettings,
    Claims,
    SessionRevoked,
    TokenError,
    check_session,
    cookie_name,
    decode_claims,
    has,
    read_bearer_or_cookie,
)
from bond_service_kit import ApiError
from fastapi import Request
from sqlalchemy.orm import Session

from .db import session_scope
from .models.auth import User

APP_NAME = "sdk_example"
COOKIE = cookie_name(APP_NAME)


class UsersRevocation:
    """``RevocationCheck`` backed by ``users.sessions_valid_after``."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def sessions_valid_after(self, user_id: str) -> datetime | None:
        user = self.session.get(User, user_id)
        return user.sessions_valid_after if user is not None else None


def refusal(exc: AuthRefused) -> ApiError:
    """An auth refusal in the shared error body."""
    return ApiError(exc.code, exc.message, status=exc.status, hint=exc.hint)


def invalid_token(message: str = "The sign-in could not be verified. Sign in again.") -> ApiError:
    return ApiError(INVALID_TOKEN, message, status=401)


def auth_settings(request: Request) -> AuthSettings:
    return request.app.state.auth_settings


def _load(request: Request) -> tuple[Claims, User]:
    cached = getattr(request.state, "auth", None)
    if cached is not None:
        return cached
    token = read_bearer_or_cookie(request.headers, request.cookies, COOKIE)
    if not token:
        raise invalid_token("Sign in to continue.")
    try:
        claims = decode_claims(token, auth_settings(request))
    except TokenError:
        raise invalid_token() from None
    with session_scope(request.app.state.session_factory) as session:
        try:
            check_session(claims, UsersRevocation(session))  # before is_active: one answer for every dead session
        except SessionRevoked as exc:
            raise refusal(exc) from None
        user = session.get(User, claims.user_id)
        if user is None:
            raise invalid_token()
        if not user.is_active:
            raise refusal(AuthRefused(DEACTIVATED))
    request.state.auth = (claims, user)
    return claims, user


def current_claims(request: Request) -> Claims:
    """The verified session claims (401 invalid_token / session_revoked, 403 deactivated)."""
    return _load(request)[0]


def current_user(request: Request) -> User:
    """The users row behind the session (detached, fully loaded)."""
    return _load(request)[1]


def current_user_id(request: Request) -> str:
    return _load(request)[0].user_id


def require_capability(cap: str):
    """A dependency that returns the user id when the user row holds ``cap``, else 403 ``forbidden``."""

    def dependency(request: Request) -> str:
        _, user = _load(request)
        if not has(list(user.capabilities or []), cap):
            raise ApiError("forbidden", f"This needs the {cap} capability.", status=403)
        return user.id

    return dependency
