"""``POST /auth/signin/{p}/start`` and ``GET /auth/signin/{p}/callback`` (web side; native calls into routes_native)."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import routes_native
from ._callback import issue_for, run_callback
from ._common import NONCE_MAX_AGE, NONCE_PATH, Deps, read_json, redirect
from .errors import http_error, raise_for
from .finish import finish_session
from .origin import require_origin
from .settings import origin_of


def _flow_start(deps: Deps, **kwargs: Any):
    try:
        return deps.flow.start(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise_for(exc)


def start_web(deps: Deps, request: Request, provider: str, body: dict) -> Response:
    require_origin(request, deps.settings)
    redirect_to = body.get("redirect_to")
    if not isinstance(redirect_to, str) or not _origin_allowed(deps, redirect_to):
        raise http_error("invalid_request")
    started = _flow_start(deps, provider=provider, scopes=deps.policy.signin_scopes(provider),
                          redirect_to=redirect_to)
    reply = JSONResponse({"url": started.url}, headers={"Cache-Control": "no-store"})
    reply.set_cookie(deps.nonce_cookie(started.nonce), started.nonce, httponly=True, samesite="lax",
                     path=NONCE_PATH, max_age=NONCE_MAX_AGE, secure=deps.settings.cookie_secure)
    return reply


def _origin_allowed(deps: Deps, url: str) -> bool:
    origin = origin_of(url)
    return origin is not None and origin in deps.settings.allowed_origins


def _invalid_state() -> JSONResponse:
    exc = http_error("invalid_state")
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def callback_web(deps: Deps, request: Request, provider: str, state: str, code: str | None,
                 error: str | None, info: Any) -> Response:
    nonce = info.nonce or ""
    name = deps.nonce_cookie(nonce)
    cookie = request.cookies.get(name)
    if not nonce or not cookie or not hmac.compare_digest(cookie.encode(), nonce.encode()) or not _origin_allowed(deps, info.redirect_to):
        # the target came from an untrusted link: no redirect, nothing recorded; drop the flow's cookie if it has one
        reply = _invalid_state()
        if nonce:
            reply.delete_cookie(name, path=NONCE_PATH, secure=deps.settings.cookie_secure, httponly=True,
                                samesite="lax")
        return reply

    def on_success(session: Any, user: Any, result: Any, first: bool) -> Any:
        if result.pending is not None:
            deps.flow.store(session, deps.connection_model, owner=user.id, result=result)
        return issue_for(deps, session, user, result, provider)

    def on_refused(reason: str) -> Response:
        return redirect(info.redirect_to, signin="error", reason=reason)

    outcome = run_callback(deps, request, provider, state=state, code=code, error=error, info=info, nonce=nonce,
                           on_success=on_success, on_refused=on_refused)
    if isinstance(outcome, Response):
        reply = outcome
    else:
        reply = redirect(info.redirect_to, signin="ok")
        finish_session(reply, outcome, settings=deps.settings, cookies=deps.cookies, delivery="cookie")
    reply.delete_cookie(name, path=NONCE_PATH, secure=deps.settings.cookie_secure, httponly=True, samesite="lax")
    return reply


def register(router: APIRouter, deps: Deps) -> None:
    @router.post("/auth/signin/{provider}/start")
    async def start(provider: str, request: Request) -> Response:
        deps.limit(request, "signin_start")
        deps.require_provider(provider)
        body = await read_json(request)
        mode = body.get("mode", "web")
        if mode not in ("web", "native"):
            raise http_error("invalid_request")
        handler = start_web if mode == "web" else routes_native.start_native
        return await run_in_threadpool(handler, deps, request, provider, body)

    @router.get("/auth/signin/{provider}/callback")
    def callback(provider: str, request: Request, state: str | None = None, code: str | None = None,
                 error: str | None = None) -> Response:
        deps.limit(request, "signin_callback")
        deps.require_provider(provider)
        if not state:
            raise http_error("invalid_state")
        try:
            info = deps.flow.peek(state=state)
        except Exception as exc:  # noqa: BLE001
            raise_for(exc)
        if info.provider != provider:
            raise http_error("invalid_state")  # a state minted for another provider's flow
        if info.native:
            return routes_native.callback_native(deps, request, provider, state, code, error, info)
        return callback_web(deps, request, provider, state, code, error, info)
