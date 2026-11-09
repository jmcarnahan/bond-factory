"""The callback core shared by web and native: complete, run the order, then hand to the caller's success step."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from fastapi import Request

from ._common import Deps
from .errors import LOGGER, STATUS_FOR_CODE, raise_for, refusal_code
from .order import sign_in_with_first
from .protocols import SignInResult, StateInfo, UserRef

Success = Callable[[Any, UserRef, SignInResult, bool], Any]
Refused = Callable[[str], Any]


def auth_time_of(result: SignInResult) -> float:
    return float(result.identity.auth_time or time.time())


def issue_for(deps: Deps, session: Any, user: UserRef, result: SignInResult, provider: str):
    spec = deps.directory.session_spec(session, user)
    return deps.sessions.issue(session, user_id=user.id, auth_time=auth_time_of(result), provider=provider,
                               spec=spec, now=deps.now())


def record_upstream(deps: Deps, request: Request, reason: str, provider: str) -> None:
    """Audit a refusal that happened before an identity existed (no e-mail, no user), committed on its own."""
    with deps.scope() as session:
        deps.directory.record_refusal(session, reason, email=None, user=None, provider=provider,
                                      ip=deps.client_ip(request))


def known_code(exc: BaseException) -> str:
    """The code of ``exc`` when it has a known one; otherwise raise it (no code) or a 500 (unknown code)."""
    code = refusal_code(exc)
    if code is None or code not in STATUS_FOR_CODE:
        raise_for(exc)
    return code  # type: ignore[return-value]


def run_callback(deps: Deps, request: Request, provider: str, *, state: str, code: str | None, error: str | None,
                 info: StateInfo, nonce: str | None, on_success: Success, on_refused: Refused) -> Any:
    """Provider error or exchange refusal -> ``on_refused(code)`` with nothing written. Otherwise the order runs in
    one transaction (a refusal there is recorded and committed, then ``on_refused``); on success ``on_success``
    stores the connection, issues, does the bookkeeping, inside the same transaction."""
    if getattr(info, "expired", False):  # authentic but old: tell the person, do not exchange anything
        record_upstream(deps, request, "signin_expired", provider)
        return on_refused("signin_expired")
    if error:
        reason = "consent_declined" if error == "access_denied" else "provider_error"
        record_upstream(deps, request, reason, provider)
        return on_refused(reason)
    if not code:
        return on_refused("invalid_request")
    try:
        result = deps.flow.complete(state=state, code=code, expected_nonce=nonce,
                                    expected_device_hash=info.device_hash if info.native else None)
    except Exception as exc:
        reason = refusal_code(exc)
        if reason is None:
            raise
        if reason == "invalid_state":
            record_upstream(deps, request, reason, provider)
            raise_for(exc)
        if reason not in STATUS_FOR_CODE:  # a provider's own error string: not ours to map, shown as provider_error
            LOGGER.warning("unmapped provider error code %r", reason[:64])
            reason = "provider_error"
        record_upstream(deps, request, reason, provider)
        return on_refused(reason)
    refused: str | None = None
    out: Any = None
    with deps.scope() as session:
        try:
            user, first = sign_in_with_first(session, directory=deps.directory, identity=result.identity,
                                             provider=provider, ip=deps.client_ip(request),
                                             now=deps.now_dt())
        except Exception as exc:  # noqa: BLE001
            refused = known_code(exc)
        else:
            out = on_success(session, user, result, first)
            deps.directory.record_sign_in(session, user, provider=provider, ip=deps.client_ip(request), first=first)
    return on_refused(refused) if refused else out
