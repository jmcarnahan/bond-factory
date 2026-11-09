"""``rotate``: exchange a refresh token for a new access token and a new refresh token.

Claim, then decide. The claim is one atomic ``UPDATE ... WHERE token_hash = ? AND rotated_at IS NULL AND revoked_at
IS NULL``; the row count says who won, on SQLite and Postgres alike, with no lock held across a request.
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy import select, update

from bond_auth_py.errors import RefreshExpired, RefreshRevoked, ReuseDetected
from bond_auth_py.session import RevocationCheck
from bond_auth_py.sessions_base import (
    IssuedSession,
    SessionSpec,
    add_row,
    clean_rotation_id,
    hash_or_refuse,
    mint_access,
    revoke_family,
    to_epoch,
    to_naive,
)
from bond_auth_py.settings import AuthSettings

HOUR = 3600.0
LOGGER = logging.getLogger(__name__)


def rotate(session, model, *, refresh_token: str, rotation_id: str | None = None, settings: AuthSettings,
           loader: Callable[[str], SessionSpec | None], revocation: RevocationCheck,
           probe: Callable[[str, str], bool | None] | None = None, now: float | None = None) -> IssuedSession:
    """Rotate ``refresh_token``. Raises ``RefreshRevoked`` (unknown, malformed, revoked, user gone or invalidated,
    IdP probe failed), ``RefreshExpired`` (sliding expiry or the absolute cap; the token is not burned) or
    ``ReuseDetected`` (the family is revoked and COMMITTED first: a ``session_scope`` that rolls back on the
    exception must not undo the revocation).

    ``loader(user_id)`` returns the JWT content for a live user, or ``None`` (deactivated, removed).
    ``rotation_id`` is the client's random id for this refresh: a replay of the same parent with the same id while
    the child is still unused is a lost response, answered with a fresh sibling (the unused child is revoked).
    Without it, a replay inside ``refresh_reuse_grace_seconds`` also gets a sibling; later is reuse.
    ``probe(user_id, provider)`` runs at most once per ``refresh_probe_hours`` per family: ``False`` revokes it;
    ``True``, ``None`` or an exception stamp the family (next probe in 24 h). It runs INSIDE the write transaction:
    keep it fast, or return ``None``.
    The revocation mark is compared with the FAMILY's ``auth_time``, never with ``now``.
    """
    t = time.time() if now is None else now
    stamp = to_naive(t)
    digest = hash_or_refuse(refresh_token)
    rotation_id = clean_rotation_id(rotation_id)
    claimed = session.execute(
        update(model).where(model.token_hash == digest, model.rotated_at.is_(None), model.revoked_at.is_(None))
        .values(rotated_at=stamp, last_used_at=stamp).execution_options(synchronize_session=False)).rowcount
    row = session.execute(select(model).where(model.token_hash == digest)
                          .execution_options(populate_existing=True)).scalar_one_or_none()
    if row is None or row.revoked_at is not None or (not claimed and row.rotated_at is None):
        raise RefreshRevoked()
    if not claimed:
        _check_replay(session, model, row, rotation_id=rotation_id, t=t, settings=settings)
    return _issue_child(session, model, row, claimed=bool(claimed), t=t, rotation_id=rotation_id,
                        settings=settings, loader=loader, revocation=revocation, probe=probe)


def _check_replay(session, model, row, *, rotation_id: str | None, t: float, settings: AuthSettings) -> None:
    """The token was already rotated. Return when it is a retry or a replay inside the grace window (the caller
    issues a sibling); otherwise revoke the family, commit, and raise ``ReuseDetected``."""
    # The retry window is anchored on the parent's FIRST rotation, so repeated retries cannot slide it.
    if rotation_id and t - to_epoch(row.rotated_at) <= settings.refresh_retry_seconds:
        child = session.execute(
            select(model).where(model.parent_id == row.id, model.rotation_id == rotation_id,
                                model.last_used_at.is_(None), model.revoked_at.is_(None))
            .order_by(model.created_at.desc())).scalars().first()
        if child is not None:
            session.execute(update(model).where(model.id == child.id)
                            .values(revoked_at=to_naive(t), revoke_reason="retry")
                            .execution_options(synchronize_session="fetch"))
            return
    grace = settings.refresh_reuse_grace_seconds
    if grace > 0 and t - to_epoch(row.rotated_at) < grace:
        return  # lost response or two tabs: not theft
    revoke_family(session, model, family_id=row.family_id, reason="reuse", now=t)
    session.commit()  # BEFORE raising: a rolling-back session_scope would otherwise undo the revocation
    raise ReuseDetected()


def _probe(probe, user_id: str, provider: str, family_id: str) -> bool | None:
    """Run the liveness probe; any exception counts as ``None`` (unknown): an IdP outage must never break refresh.
    Only the exception type and the family id are logged."""
    try:
        return probe(user_id, provider)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("session liveness probe failed (%s) for family %s", type(exc).__name__, family_id)
        return None


def _unclaim(session, model, row, stamp) -> None:
    session.execute(update(model).where(model.id == row.id, model.rotated_at == stamp)
                    .values(rotated_at=None, last_used_at=None).execution_options(synchronize_session="fetch"))


def _end_family(session, model, row, *, reason: str, t: float) -> None:
    revoke_family(session, model, family_id=row.family_id, reason=reason, now=t)
    session.commit()
    raise RefreshRevoked()


def _issue_child(session, model, row, *, claimed: bool, t: float, rotation_id: str | None,
                 settings: AuthSettings, loader, revocation, probe) -> IssuedSession:
    stamp = to_naive(t)
    parent_id, family_id, user_id = row.id, row.family_id, row.user_id
    provider, auth_time, family_cap = row.provider, row.auth_time, row.family_expires_at
    label, probed = row.device_label, row.last_probed_at
    if t >= to_epoch(row.expires_at) or t >= to_epoch(family_cap):
        if claimed:
            _unclaim(session, model, row, stamp)  # an expired token is not burned
        raise RefreshExpired()
    try:
        spec = loader(user_id)
        valid_after = revocation.sessions_valid_after(user_id) if spec is not None else None
        stale = valid_after is not None and _stale(auth_time, valid_after, settings)
        due = probe is not None and (probed is None or t - to_epoch(probed) >= settings.refresh_probe_hours * HOUR)
        alive = _probe(probe, user_id, provider, family_id) if (spec is not None and not stale and due) else None
    except Exception:
        if claimed:
            _unclaim(session, model, row, stamp)
        raise
    if spec is None:
        _end_family(session, model, row, reason="admin", t=t)
    if stale:
        _end_family(session, model, row, reason="signout_all", t=t)
    if alive is False:
        _end_family(session, model, row, reason="admin", t=t)
    if due:
        probed = stamp
    token = add_row(session, model, user_id=user_id, family_id=family_id, provider=provider, auth_time=auth_time,
                    family_expires_at=family_cap, t=t, settings=settings, parent_id=parent_id,
                    rotation_id=rotation_id, device_label=label, last_probed_at=probed)
    access, expires_in = mint_access(spec, family_id=family_id, settings=settings, t=t)
    return IssuedSession(access_jwt=access, refresh_token=token, family_id=family_id, expires_in=expires_in,
                         user_id=user_id)


def _stale(auth_time, valid_after, settings: AuthSettings) -> bool:
    """The family's sign-in predates the revocation mark (5 s skew), as ``check_exchange`` does."""
    return to_epoch(auth_time) + settings.auth_time_skew_seconds < to_epoch(valid_after)
