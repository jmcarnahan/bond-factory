"""Session revocation: ``users.sessions_valid_after`` (nullable UTC datetime) is the authority on "sign out
everywhere", deactivate, remove and e-mail change. Always compared on the real clock.
"""

from datetime import UTC, datetime
from typing import Protocol

from bond_auth_py.errors import SessionRevoked, TokenError
from bond_auth_py.settings import AuthSettings
from bond_auth_py.tokens import Claims
from bond_auth_py.verify import Identity


class RevocationCheck(Protocol):
    def sessions_valid_after(self, user_id: str) -> datetime | None: ...


def _epoch(value: datetime) -> float:
    """Naive datetimes are UTC (that is how the column is stored)."""
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).timestamp()


def check_session(claims: Claims, revocation: RevocationCheck, *, now: datetime | None = None) -> None:
    """Raise ``SessionRevoked`` when the token was issued before ``sessions_valid_after``.

    Call it BEFORE any ``is_active`` check, so an old token of a deactivated person gets the same answer as any
    other dead session. A token without a usable ``iat`` cannot be proven newer and is refused as invalid.
    ``now`` is accepted for symmetry with ``check_exchange`` and is not used: the comparison is iat against the mark.
    """
    valid_after = revocation.sessions_valid_after(claims.user_id)
    if valid_after is None:
        return
    try:
        issued = float(claims.iat)
    except (TypeError, ValueError):
        raise TokenError("invalid") from None
    if issued < _epoch(valid_after):
        raise SessionRevoked()


def check_exchange(identity: Identity, revocation: RevocationCheck, settings: AuthSettings, *, user_id: str,
                   now: datetime | None = None) -> None:
    """Refuse an ID token from a sign-in older than the revocation mark: ``auth_time + skew < sessions_valid_after``.

    A refresh-token-driven ID token keeps its old ``auth_time``, so it fails here until the person signs in again.
    A missing ``auth_time`` is refused too (it cannot be proven newer).
    """
    valid_after = revocation.sessions_valid_after(user_id)
    if valid_after is None:
        return
    if identity.auth_time is None or identity.auth_time + settings.auth_time_skew_seconds < _epoch(valid_after):
        raise SessionRevoked()
