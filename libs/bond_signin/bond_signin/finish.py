"""``finish_session``: every sign-in path (callback, redeem, break-glass, demo, refresh) ends here."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Response

from .protocols import IssuedSession
from .settings import SignInSettings


@dataclass(frozen=True)
class CookiePolicy:
    """Names and ``set_cookie`` keyword arguments of the two session cookies (from the sessions lib's settings)."""

    access_name: str
    refresh_name: str
    access_cookie: Callable[[bool], dict]
    refresh_cookie: Callable[[bool], dict]
    refresh_path: str | None = None  # the router sets it from its prefix; overrides the callable's ``path``

    def refresh_params(self, secure: bool) -> dict:
        params = dict(self.refresh_cookie(secure))
        if self.refresh_path:
            params["path"] = self.refresh_path
        return params


def finish_session(response: Response, issued: IssuedSession, *, settings: SignInSettings, cookies: CookiePolicy,
                   delivery: str | None = None) -> dict[str, Any]:
    """Set the cookies (``delivery="cookie"``: access and refresh, no refresh token in the body) or set none and put
    the refresh token in the body (``"body"``). Returns the session part of the JSON answer."""
    mode = delivery or settings.delivery_web
    body: dict[str, Any] = {"token": issued.access_jwt, "expires_in": issued.expires_in}
    if mode == "cookie":
        secure = settings.cookie_secure
        response.set_cookie(cookies.access_name, issued.access_jwt, **cookies.access_cookie(secure))
        response.set_cookie(cookies.refresh_name, issued.refresh_token, **cookies.refresh_params(secure))
    else:
        body["refresh_token"] = issued.refresh_token
    return body


def clear_session_cookies(response: Response, *, settings: SignInSettings, cookies: CookiePolicy) -> None:
    """Delete the access and refresh cookies on the paths they were set on."""
    secure = settings.cookie_secure
    for name, params in ((cookies.access_name, cookies.access_cookie(secure)),
                         (cookies.refresh_name, cookies.refresh_params(secure))):
        response.delete_cookie(name, path=params.get("path", "/"), secure=secure, httponly=True, samesite="lax")
