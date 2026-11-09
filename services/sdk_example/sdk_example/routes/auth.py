"""Sign-in and session routes under /auth: firebase, refresh, demo, providers, me, logout."""

from __future__ import annotations

import re
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
    create_access_token,
    not_invited,
    providers_payload,
    session_cookie_params,
    verify_id_token,
)
from bond_service_kit import ApiError
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..auth_dep import COOKIE, UsersRevocation, auth_settings, current_user, invalid_token, refusal
from ..db import session_scope
from ..models.auth import User, utcnow
from ..wiring import client_ip

LANGUAGE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
CurrentUser = Annotated[User, Depends(current_user)]


class IdTokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=1, max_length=8192)
    #: false = a renewal: skips the accepted / last-sign-in updates. /auth/refresh is always a renewal.
    sign_in: bool = True


class DemoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=64)


class MeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str = Field(pattern=LANGUAGE.pattern)


def rate_limit_exchange(request: Request) -> None:
    request.app.state.limiters["auth"].check(f"exchange:{client_ip(request)}")


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


def _session_answer(request: Request, response: Response, user: User) -> dict:
    settings = auth_settings(request)
    token = create_access_token(sub=user.id, name=user.name, capabilities=list(user.capabilities or []),
                                settings=settings)
    secure = request.app.state.settings.mode != "fake"
    response.set_cookie(COOKIE, token, **session_cookie_params(settings, secure=secure))
    return {"token": token, "user": user.public()}


def _exchange(request: Request, response: Response, id_token: str, *, sign_in: bool) -> dict:
    settings = auth_settings(request)
    identity = _verify(id_token, settings)
    try:
        with session_scope(request.app.state.session_factory) as session:
            user = session.execute(select(User).where(User.email == identity.email)).scalar_one_or_none()
            if user is None:
                raise not_invited(identity.email)
            if user.firebase_uid and user.firebase_uid != identity.uid:
                raise AuthRefused(IDENTITY_MISMATCH)
            check_exchange(identity, UsersRevocation(session), settings, user_id=user.id)
            if not user.is_active:
                raise AuthRefused(DEACTIVATED)
            if sign_in:
                now = utcnow()
                user.firebase_uid = user.firebase_uid or identity.uid
                user.accepted_at = user.accepted_at or now
                user.last_sign_in_at = now
            answer = _session_answer(request, response, user)
    except AuthRefused as exc:
        raise refusal(exc) from None
    return answer


def register(app: FastAPI) -> None:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/firebase", dependencies=[Depends(rate_limit_exchange)])
    def firebase(body: IdTokenBody, request: Request, response: Response) -> dict:
        return _exchange(request, response, body.id_token, sign_in=body.sign_in)

    @router.post("/refresh", dependencies=[Depends(rate_limit_exchange)])
    def refresh(body: IdTokenBody, request: Request, response: Response) -> dict:
        return _exchange(request, response, body.id_token, sign_in=False)

    @router.post("/demo")
    def demo(body: DemoBody, request: Request, response: Response) -> dict:
        if not auth_settings(request).demo_enabled:
            raise ApiError("not_found", "Not found", status=404)
        with session_scope(request.app.state.session_factory) as session:
            user = session.get(User, body.user_id)
            if user is None:
                raise ApiError("not_found", "No such demo user.", status=404)
            if not user.is_active:
                raise refusal(AuthRefused(DEACTIVATED))
            user.last_sign_in_at = utcnow()
            return _session_answer(request, response, user)

    @router.get("/providers")
    def providers(request: Request) -> dict:
        settings = request.app.state.settings
        return providers_payload(auth_settings(request), sync_url=settings.sync_url or None,
                                 mock=True if settings.mode == "fake" else None)

    @router.get("/me")
    def me(user: CurrentUser) -> dict:
        return {"user": user.public()}

    @router.patch("/me")
    def patch_me(body: MeBody, request: Request, user: CurrentUser) -> dict:
        with session_scope(request.app.state.session_factory) as session:
            row = session.get(User, user.id)
            row.language = body.language
            return {"user": row.public()}

    @router.post("/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(COOKIE, path="/")
        return {"status": "logged_out"}

    app.include_router(router)
