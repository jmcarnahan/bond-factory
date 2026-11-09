"""``POST /auth/refresh``, ``POST /auth/logout``, ``POST /auth/sessions/revoke-all``."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ._callback import known_code
from ._common import Deps, read_json
from .errors import MESSAGES, STATUS_FOR_CODE, http_error
from .finish import clear_session_cookies, finish_session
from .origin import has_bearer, require_origin

LOGGER = logging.getLogger("bond_signin")
REFRESH_CODES = ("refresh_reused", "refresh_expired", "refresh_revoked")


class _Revocation:
    """``RevocationCheck`` over the directory: ``sessions_valid_after`` of the user."""

    def __init__(self, deps: Deps, session: Any) -> None:
        self.deps, self.session = deps, session

    def sessions_valid_after(self, user_id: str) -> datetime | None:
        user = self.deps.directory.find_by_id(self.session, user_id)
        return user.sessions_valid_after if user is not None else None


def _error(deps: Deps, code: str, *, clear: bool) -> Response:
    reply = JSONResponse(status_code=STATUS_FOR_CODE[code], content={"detail": {"code": code,
                                                                                "message": MESSAGES[code]}})
    if clear:
        clear_session_cookies(reply, settings=deps.settings, cookies=deps.cookies)
    return reply


def rotate_sync(deps: Deps, request: Request, token: str, rotation_id: str | None, delivery: str) -> Response:
    loaded: dict[str, Any] = {}
    failure: Exception | None = None
    answer: dict[str, Any] = {}
    issued = None
    with deps.scope() as session:
        def loader(user_id: str):
            user = deps.directory.find_by_id(session, user_id)
            if user is None or not user.is_active:
                return None
            loaded["user"] = user
            return deps.directory.session_spec(session, user)

        def probe(user_id: str, provider: str) -> bool | None:
            user = loaded.get("user") or deps.directory.find_by_id(session, user_id)
            return None if user is None else deps.directory.provider_alive(session, user, provider)

        try:
            issued = deps.sessions.rotate(session, refresh_token=token, rotation_id=rotation_id, loader=loader,
                                          revocation=_Revocation(deps, session), probe=probe, now=deps.now())
            user = loaded.get("user") or deps.directory.find_by_id(session, issued.user_id)
            answer = {"user": deps.directory.public(session, user) if user is not None else None}
        except Exception as exc:  # noqa: BLE001
            failure = exc
    if failure is not None:
        code = known_code(failure)
        return _error(deps, code, clear=delivery == "cookie" and code in REFRESH_CODES)
    reply = JSONResponse({}, headers={"Cache-Control": "no-store"})
    body = {**finish_session(reply, issued, settings=deps.settings, cookies=deps.cookies, delivery=delivery), **answer}
    reply.body = reply.render(body)
    reply.headers["content-length"] = str(len(reply.body))
    return reply


def logout_sync(deps: Deps, request: Request, token: str | None) -> Response:
    if token:
        try:
            with deps.scope() as session:
                deps.sessions.revoke_token(session, refresh_token=token, reason="logout")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("logout revoke failed (%s)", type(exc).__name__)
    reply = JSONResponse({"status": "logged_out"}, headers={"Cache-Control": "no-store"})
    clear_session_cookies(reply, settings=deps.settings, cookies=deps.cookies)
    return reply


def revoke_all_sync(deps: Deps, request: Request) -> Response:
    current = deps.session_dep(request)
    if current is None:
        raise http_error("invalid_token")
    with deps.scope() as session:
        user = deps.directory.find_by_id(session, current.id)
        if user is None:
            raise http_error("invalid_token")
        revoked = deps.sessions.revoke_user(
            session, user_id=user.id, reason="signout_all",
            mark_valid_after=lambda _uid, at: deps.directory.mark_sessions_invalid(session, user, at))
    reply = JSONResponse({"revoked": revoked}, headers={"Cache-Control": "no-store"})
    clear_session_cookies(reply, settings=deps.settings, cookies=deps.cookies)
    return reply


def register(router: APIRouter, deps: Deps) -> None:
    @router.post("/auth/refresh")
    async def refresh(request: Request) -> Any:
        deps.limit(request, "refresh")
        body = await read_json(request)
        body_token = body.get("refresh_token")
        body_token = body_token if isinstance(body_token, str) and body_token else None
        if deps.legacy_refresh is not None and "id_token" in body and not body_token:
            if not has_bearer(request):
                require_origin(request, deps.settings)  # a legacy exchange can set cookies: same rule as cookies
            return await run_in_threadpool(deps.legacy_refresh, request, body)
        # The TOKEN SOURCE decides, never the client's `delivery`: a cookie-sourced refresh is a browser request.
        from_cookie = body_token is None
        if from_cookie or body.get("delivery") == "cookie":
            require_origin(request, deps.settings)
            delivery = "cookie"
        else:
            delivery = "body"
        token = body_token or request.cookies.get(deps.cookies.refresh_name)
        if not token:
            raise http_error("invalid_token")
        rotation_id = body.get("rotation_id")
        rotation_id = rotation_id if isinstance(rotation_id, str) and 0 < len(rotation_id) <= 128 else None
        return await run_in_threadpool(rotate_sync, deps, request, token, rotation_id, delivery)

    @router.post("/auth/logout")
    async def logout(request: Request) -> Response:
        body = await read_json(request, strict=False)
        body_token = body.get("refresh_token")
        if not (isinstance(body_token, str) and body_token):
            require_origin(request, deps.settings)
            body_token = request.cookies.get(deps.cookies.refresh_name)
        return await run_in_threadpool(logout_sync, deps, request, body_token)

    @router.post("/auth/sessions/revoke-all")
    async def revoke_all(request: Request) -> Response:
        if not has_bearer(request):
            require_origin(request, deps.settings)
        return await run_in_threadpool(revoke_all_sync, deps, request)
