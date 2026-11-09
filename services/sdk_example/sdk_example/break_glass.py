"""REPLACE or DELETE. The Firebase e-mail and password route, kept only for admin rows and the store reviewer.

An app without a break-glass deletes this file, the `legacy_refresh` argument in `signin_wiring.py` and the
`allow_password` column. Off (404) unless SDK_EXAMPLE_BREAKGLASS=1, and only for rows flagged `allow_password`.
"""

from __future__ import annotations

from typing import Annotated

from bond_auth_py import (
    AUTH_UNAVAILABLE,
    DEACTIVATED,
    EMAIL_NOT_VERIFIED,
    FIREBASE_NOT_CONFIGURED,
    IDENTITY_MISMATCH,
    AuthNotConfigured,
    AuthRefused,
    AuthSettings,
    AuthUnavailable,
    EmailNotVerified,
    Identity,
    TokenError,
    check_exchange,
    not_invited,
    verify_id_token,
)
from bond_service_kit import ApiError
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .auth_dep import UsersRevocation, auth_settings, invalid_token, refusal
from .db import session_scope
from .models.auth import User, utcnow
from .session_answer import session_answer
from .wiring import client_ip

Delivery = Annotated[str | None, Field(pattern="^(cookie|body)$")]


class IdTokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=1, max_length=8192)
    sign_in: bool = True  # false = a renewal: skips the accepted / last-sign-in updates
    delivery: Delivery = None  # None = cookies (web); "body" = tokens in the answer (phone)


def _verify(token: str, settings: AuthSettings) -> Identity:
    try:
        return verify_id_token(token, settings)
    except TokenError:
        raise invalid_token() from None
    except EmailNotVerified:
        raise ApiError(EMAIL_NOT_VERIFIED, "This e-mail address has not been verified.", status=403) from None
    except AuthNotConfigured:
        raise ApiError(FIREBASE_NOT_CONFIGURED, "Firebase sign-in is not configured on this server.",
                       status=501) from None
    except AuthUnavailable:
        raise ApiError(AUTH_UNAVAILABLE, "Sign-in is temporarily unavailable. Try again shortly.",
                       status=503) from None


def exchange(request: Request, response: Response, id_token: str, *, sign_in: bool, delivery: str | None) -> dict:
    if not request.app.state.settings.breakglass:
        raise ApiError("not_found", "Not found", status=404)
    settings = auth_settings(request)
    identity = _verify(id_token, settings)
    try:
        with session_scope(request.app.state.session_factory) as session:
            user = session.execute(select(User).where(User.email == identity.email)).scalar_one_or_none()
            if user is None:
                raise not_invited(identity.email)
            if user.firebase_uid and user.firebase_uid != identity.uid:
                raise AuthRefused(IDENTITY_MISMATCH)
            if not user.allow_password:
                raise ApiError("provider_not_allowed", "This account cannot sign in with a password.", status=403)
            check_exchange(identity, UsersRevocation(session), settings, user_id=user.id)
            if not user.is_active:
                raise AuthRefused(DEACTIVATED)
            if sign_in:
                now = utcnow()
                user.firebase_uid = user.firebase_uid or identity.uid
                user.accepted_at = user.accepted_at or now
                user.last_sign_in_at = now
            return session_answer(request, session, response, user, provider="password",
                                  auth_time=identity.auth_time, delivery=delivery)
    except AuthRefused as exc:
        raise refusal(exc) from None


def _reply(request: Request, id_token: str, *, sign_in: bool, delivery: str | None) -> JSONResponse:
    reply = JSONResponse({}, headers={"Cache-Control": "no-store"})
    answer = exchange(request, reply, id_token, sign_in=sign_in, delivery=delivery)
    reply.body = reply.render(answer)
    reply.headers["content-length"] = str(len(reply.body))
    return reply


def legacy_refresh(request: Request, body: dict) -> JSONResponse:
    """`POST /auth/refresh {id_token}`: the sign-in library hands a Firebase id token here (a renewal)."""
    token = body.get("id_token")
    if not isinstance(token, str) or not token:
        raise invalid_token()
    return _reply(request, token, sign_in=False, delivery=body.get("delivery"))


def register(app: FastAPI) -> None:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/firebase")
    def firebase(body: IdTokenBody, request: Request) -> Response:
        app.state.limiters["auth"].check(f"firebase:{client_ip(request)}")
        return _reply(request, body.id_token, sign_in=body.sign_in, delivery=body.delivery)

    app.include_router(router)
