"""Native sign-in: start (device-bound), callback (hands off a code), redeem (device secret -> session)."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ._callback import auth_time_of, run_callback
from ._common import Deps, read_json, redirect
from .errors import http_error, raise_for
from .finish import finish_session
from .order import SKEW_SECONDS, epoch_of

CHALLENGE = re.compile(r"^[0-9a-f]{64}$")
ATTEMPT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def return_ok(deps: Deps, provider: str, url: str) -> bool:
    return url == f"{deps.settings.native_return_base}/{provider}" or deps.settings.native_scheme_ok(url)


def start_native(deps: Deps, request: Request, provider: str, body: dict) -> Response:
    challenge, attempt, redirect_to = body.get("device_challenge"), body.get("attempt"), body.get("redirect_to")
    if not (isinstance(challenge, str) and CHALLENGE.match(challenge)):
        raise http_error("invalid_request")
    if not (isinstance(attempt, str) and ATTEMPT.match(attempt)):
        raise http_error("invalid_request")
    if not (isinstance(redirect_to, str) and return_ok(deps, provider, redirect_to)):
        raise http_error("invalid_request")
    try:
        started = deps.flow.start(provider=provider, scopes=deps.policy.signin_scopes(provider),
                                  redirect_to=redirect_to, device_hash=challenge, attempt_id=attempt)
    except Exception as exc:  # noqa: BLE001
        raise_for(exc)
    return JSONResponse({"url": started.url}, headers={"Cache-Control": "no-store"})


def callback_native(deps: Deps, request: Request, provider: str, state: str, code: str | None,
                    error: str | None, info: Any) -> Response:
    if not return_ok(deps, provider, info.redirect_to) or not info.device_hash:
        raise http_error("invalid_state")

    def on_success(session: Any, user: Any, result: Any, first: bool) -> str:
        if result.pending is not None:
            deps.flow.store(session, deps.connection_model, owner=user.id, result=result)
        payload = {"user_id": user.id, "provider": provider, "auth_time": auth_time_of(result),
                   "attempt": info.attempt_id}
        return deps.handoffs.issue(session, purpose="signin", provider=provider, payload=payload,
                                   device_hash=info.device_hash, attempt_id=info.attempt_id, now=deps.now())

    def on_refused(reason: str) -> Response:
        return redirect(info.redirect_to, attempt=info.attempt_id, error=reason)

    outcome = run_callback(deps, request, provider, state=state, code=code, error=error, info=info, nonce=None,
                           on_success=on_success, on_refused=on_refused)
    if isinstance(outcome, Response):
        return outcome
    return redirect(info.redirect_to, attempt=info.attempt_id, code=outcome)


def redeem_sync(deps: Deps, request: Request, body: dict) -> Response:
    code, secret = body.get("code"), body.get("device_secret")
    if not (isinstance(code, str) and isinstance(secret, str) and code and secret):
        raise http_error("invalid_request")
    label = body.get("device_label")
    failure: Exception | None = None
    answer: dict[str, Any] = {}
    with deps.scope() as session:
        try:
            payload = deps.handoffs.redeem(session, code=code, device_secret=secret, purpose="signin", now=deps.now())
            user = deps.directory.find_by_id(session, str(payload.get("user_id", "")))
            if user is None or not user.is_active:
                raise http_error("deactivated")
            auth_time = float(payload.get("auth_time") or 0)
            if user.sessions_valid_after is not None and epoch_of(user.sessions_valid_after) > auth_time + SKEW_SECONDS:
                raise http_error("session_revoked")
            spec = deps.directory.session_spec(session, user)
            issued = deps.sessions.issue(
                session, user_id=user.id, auth_time=auth_time, provider=str(payload.get("provider", "")),
                spec=spec, device_label=label[:80] if isinstance(label, str) else None,
                now=deps.now())
            answer = {**finish_session(JSONResponse({}), issued, settings=deps.settings, cookies=deps.cookies,
                                       delivery="body"),
                      "user": deps.directory.public(session, user)}
        except Exception as exc:  # noqa: BLE001
            failure = exc
    if failure is not None:
        raise_for(failure)
    return JSONResponse(answer, headers={"Cache-Control": "no-store"})


def register(router: APIRouter, deps: Deps) -> None:
    @router.post(f"{deps.prefix}/signin/redeem")
    async def redeem(request: Request) -> Response:
        deps.limit(request, "redeem")
        body = await read_json(request)
        return await run_in_threadpool(redeem_sync, deps, request, body)
