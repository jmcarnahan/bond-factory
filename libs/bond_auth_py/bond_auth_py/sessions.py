"""Own rotating refresh-token sessions (``auth_sessions``), the access JWT they mint, and their revocation.

Lifetimes (``AuthSettings``): access JWT ``session_access_ttl_minutes`` (60); refresh token ``refresh_ttl_days``
sliding (60), capped at ``refresh_max_days`` (180) from the IdP sign-in instant; ``refresh_max_sessions_per_user``
(10) live families. The model is passed in (a class built on ``SessionsMixin``); ``SessionStore`` binds it.
Functions flush but never commit, with one exception: ``rotate`` commits before it raises ``ReuseDetected`` or
ends a family, so a rolling-back ``session_scope`` cannot undo the revocation.
"""

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update

from bond_auth_py.session import RevocationCheck
from bond_auth_py.sessions_base import (
    DAY,
    IssuedSession,
    SessionSpec,
    add_row,
    hash_or_refuse,
    mint_access,
    revoke_family,
    to_naive,
)
from bond_auth_py.sessions_rotate import rotate
from bond_auth_py.settings import AuthSettings

__all__ = ["IssuedSession", "SessionSpec", "SessionStore", "issue_session", "prune_sessions", "revoke_family",
           "revoke_token", "revoke_user", "rotate"]


def issue_session(session, model, *, user_id: str, auth_time: float, provider: str, spec: SessionSpec,
                  settings: AuthSettings, device_label: str | None = None, now: float | None = None
                  ) -> IssuedSession:
    """Start a session family after a sign-in. ``auth_time`` is the IdP sign-in instant (epoch seconds): the
    absolute cap and the revocation mark are measured from it. When the user already has
    ``refresh_max_sessions_per_user`` live families, the least recently used one is revoked (reason ``limit``)."""
    t = time.time() if now is None else now
    limit = settings.refresh_max_sessions_per_user
    if limit > 0:
        live = session.execute(
            select(model.family_id).where(model.user_id == user_id, model.revoked_at.is_(None),
                                          model.rotated_at.is_(None))
            .group_by(model.family_id).order_by(func.max(model.created_at), model.family_id)).scalars().all()
        for family_id in live[:max(0, len(live) - limit + 1)]:
            revoke_family(session, model, family_id=family_id, reason="limit", now=t)
    family_id = str(uuid.uuid4())
    token = add_row(session, model, user_id=user_id, family_id=family_id, provider=provider,
                    auth_time=to_naive(auth_time),
                    family_expires_at=to_naive(auth_time + settings.refresh_max_days * DAY),
                    t=t, settings=settings, parent_id=None, rotation_id=None, device_label=device_label,
                    last_probed_at=None)
    access, expires_in = mint_access(spec, family_id=family_id, settings=settings, t=t)
    return IssuedSession(access_jwt=access, refresh_token=token, family_id=family_id, expires_in=expires_in,
                         user_id=user_id)


def revoke_token(session, model, *, refresh_token: str, reason: str = "logout", now: float | None = None) -> bool:
    """Revoke the family of ``refresh_token`` (logout). ``True`` when something was revoked; idempotent, and
    ``False`` for an unknown, malformed or already ended token (never an error)."""
    try:
        digest = hash_or_refuse(refresh_token)
    except Exception:  # noqa: BLE001 - logout never fails
        return False
    family_id = session.execute(select(model.family_id).where(model.token_hash == digest)).scalar_one_or_none()
    if family_id is None:
        return False
    return revoke_family(session, model, family_id=family_id, reason=reason, now=now) > 0


def revoke_user(session, model, *, user_id: str, reason: str = "admin",
                mark_valid_after: Callable[[str, datetime], None] | None = None, now: float | None = None) -> int:
    """Revoke every live row of the user and, in the same transaction, call ``mark_valid_after(user_id, when)``
    (``when`` is an aware UTC datetime) so access tokens and exchanges issued earlier die too. Returns rows
    revoked. The caller commits."""
    t = time.time() if now is None else now
    count = session.execute(
        update(model).where(model.user_id == user_id, model.revoked_at.is_(None))
        .values(revoked_at=to_naive(t), revoke_reason=reason[:16]).execution_options(synchronize_session="fetch")
    ).rowcount or 0
    if mark_valid_after is not None:
        mark_valid_after(user_id, datetime.fromtimestamp(t, UTC))
    return count


def prune_sessions(session, model, *, now: float | None = None, keep_revoked_days: int = 7,
                   keep_rotated_days: int | None = 7) -> int:
    """Delete rows that can no longer matter: expired or revoked more than ``keep_revoked_days`` ago (kept that
    long so a replay answers "revoked", not "unknown"), and rotated parents older than ``keep_rotated_days``
    (``None`` keeps them until they expire; after the delete a replay of that parent is "unknown")."""
    t = time.time() if now is None else now
    cutoff = to_naive(t - keep_revoked_days * DAY)
    conditions = [model.expires_at < cutoff, model.revoked_at < cutoff]
    if keep_rotated_days is not None:
        conditions.append(model.rotated_at < to_naive(t - keep_rotated_days * DAY))
    return session.execute(delete(model).where(or_(*conditions)).execution_options(
        synchronize_session=False)).rowcount or 0


class SessionStore:
    """``model`` and ``settings`` bound once. Structurally what ``bond_signin.SessionIssuer`` expects."""

    def __init__(self, model, settings: AuthSettings):
        self.model = model
        self.settings = settings

    def issue(self, session, *, user_id: str, auth_time: float, provider: str, spec: SessionSpec,
              device_label: str | None = None, now: float | None = None) -> IssuedSession:
        return issue_session(session, self.model, user_id=user_id, auth_time=auth_time, provider=provider,
                             spec=spec, settings=self.settings, device_label=device_label, now=now)

    def rotate(self, session, *, refresh_token: str, rotation_id: str | None,
               loader: Callable[[str], SessionSpec | None], revocation: RevocationCheck,
               probe: Callable[[str, str], bool | None] | None = None, now: float | None = None
               ) -> IssuedSession:
        """Raises ``RefreshRevoked`` / ``RefreshExpired`` / ``ReuseDetected`` (codes ``refresh_revoked``,
        ``refresh_expired``, ``refresh_reused``)."""
        return rotate(session, self.model, refresh_token=refresh_token, rotation_id=rotation_id,
                      settings=self.settings, loader=loader, revocation=revocation, probe=probe, now=now)

    def revoke_token(self, session, *, refresh_token: str, reason: str = "logout") -> bool:
        return revoke_token(session, self.model, refresh_token=refresh_token, reason=reason)

    def revoke_user(self, session, *, user_id: str, reason: str = "admin",
                    mark_valid_after: Callable[[str, datetime], None] | None = None) -> int:
        return revoke_user(session, self.model, user_id=user_id, reason=reason, mark_valid_after=mark_valid_after)

    def prune(self, session, now: float | None = None) -> int:
        return prune_sessions(session, self.model, now=now)
