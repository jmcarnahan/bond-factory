"""The fixed refusal order, the same for every app (decision D11).

``tenant_mismatch`` is raised upstream by the identity flow. Here: ``email_not_verified`` -> ``not_invited`` ->
``check_allowed`` -> ``deactivated`` -> ``identity_mismatch`` -> ``session_revoked`` -> link. On ANY refusal
``record_refusal`` runs and the exception is re-raised. Nothing is stored here: the caller stores after this returns.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from .errors import SignInRefused, refusal_code
from .policy import normalize_email
from .protocols import OidcIdentity, UserDirectory, UserRef

SKEW_SECONDS = 5.0


def _verified(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return value is True


def epoch_of(moment: datetime) -> float:
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp()


def sign_in_with_first(session: Any, *, directory: UserDirectory, identity: OidcIdentity, provider: str,
                       ip: str | None, now: datetime | None = None) -> tuple[UserRef, bool]:
    """Run the order. Returns ``(user, first)``; ``first`` is true when this sign-in bound the identity."""
    user: UserRef | None = None
    try:
        return _run(session, directory, identity, provider, now)
    except Exception as exc:
        code = refusal_code(exc)
        if code is not None:
            user = getattr(exc, "user", None)
            directory.record_refusal(session, code, email=getattr(identity, "email", None), user=user,
                                     provider=provider, ip=ip)
        raise


def sign_in(session: Any, *, directory: UserDirectory, identity: OidcIdentity, provider: str, ip: str | None,
            now: datetime | None = None) -> UserRef:
    """``sign_in_with_first`` without the ``first`` flag."""
    return sign_in_with_first(session, directory=directory, identity=identity, provider=provider, ip=ip,
                              now=now)[0]


def _refuse(code: str, user: UserRef | None) -> SignInRefused:
    exc = SignInRefused(code)
    exc.user = user  # type: ignore[attr-defined]
    return exc


def _run(session: Any, directory: UserDirectory, identity: OidcIdentity, provider: str,
         now: datetime | None) -> tuple[UserRef, bool]:
    if not _verified(identity.email_verified):
        raise _refuse("email_not_verified", None)
    subject = identity.subject
    user = directory.find_by_identity(session, provider, subject)
    invited = user is None
    if user is None:
        emails = [identity.email.strip().lower(), normalize_email(provider, identity.email)]
        user = directory.find_invite(session, list(dict.fromkeys(e for e in emails if e)), provider)
        if user is None:
            raise _refuse("not_invited", None)
    try:
        directory.check_allowed(session, user, provider)
    except Exception as exc:
        if refusal_code(exc) is not None:
            exc.user = user  # type: ignore[attr-defined]
        raise
    if not user.is_active:
        raise _refuse("deactivated", user)
    if invited and user.identity is not None and tuple(user.identity) != (provider, subject):
        raise _refuse("identity_mismatch", user)
    auth_time = identity.auth_time if identity.auth_time else (now.timestamp() if now else time.time())
    valid_after = user.sessions_valid_after
    if valid_after is not None and epoch_of(valid_after) > auth_time + SKEW_SECONDS:
        raise _refuse("session_revoked", user)
    if invited:
        try:
            directory.link_identity(session, user, provider, subject)
        except Exception as exc:
            if type(exc).__name__ == "IdentityTaken" and refusal_code(exc) is None:
                raise _refuse("identity_mismatch", user) from exc
            if refusal_code(exc) is not None:
                exc.user = user  # type: ignore[attr-defined]
            raise
    return user, invited
