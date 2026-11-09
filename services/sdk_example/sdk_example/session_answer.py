"""COPY AS IS. The one way every sign-in path ends: issue a refresh session, set the cookies (web) or return the
tokens in the body (phone, `delivery: "body"`). The demo route, break-glass and the library's callbacks all agree."""

from __future__ import annotations

import time

import bond_signin
from fastapi import Request, Response
from sqlalchemy.orm import Session

from .models.auth import User


def require_cookie_origin(request: Request, delivery: str | None) -> None:
    """Login-CSRF guard for the routes that ISSUE a session (demo, break-glass): when the answer sets cookies
    (`delivery` None or "cookie") the request must come from an allowed origin, even though the caller is signed out
    and carries no cookie yet. Body delivery (a phone) sets no cookie and needs no Origin."""
    if (delivery or "cookie") == "cookie":
        bond_signin.require_origin(request, request.app.state.signin.settings)


def session_answer(request: Request, session: Session, response: Response, user: User, *, provider: str,
                   auth_time: float | None, delivery: str | None) -> dict:
    """`provider` is recorded on the session row (`demo`, `password`, or the IdP's name)."""
    stack = request.app.state.signin
    issued = stack.sessions.issue(session, user_id=user.id, auth_time=auth_time or time.time(), provider=provider,
                                  spec=stack.directory.session_spec(session, user))
    body = bond_signin.finish_session(response, issued, settings=stack.settings, cookies=stack.cookies,
                                      delivery=delivery)
    return {**body, "user": stack.directory.public(session, user)}
