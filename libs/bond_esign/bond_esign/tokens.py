"""Per-signer link tokens. Only the sha256 of a token is stored; the raw token goes to the signer once."""

import secrets
from datetime import timedelta

from sqlalchemy import select

from bond_esign import events
from bond_esign._rows import EXPIRED, iso, lock, request_of, utc
from bond_esign.errors import EXPIRED as EXPIRED_CODE
from bond_esign.errors import EsignError
from bond_esign.lifecycle import expire_if_due
from bond_esign.pdf_read import sha256_hex
from bond_esign.types import Tables


def _hash(token: str) -> str:
    return sha256_hex(token.encode("utf-8"))


def issue_token(session, t: Tables, signer, *, now, ttl_seconds: int | None = None) -> str:
    """Make a new link token for the signer (replacing any earlier one) and return it. Shown once."""
    now = utc(now)
    request = request_of(session, t, signer)
    lock(session, t, request, signer)
    if expire_if_due(session, t, request, now) or request.status == EXPIRED:
        raise EsignError(EXPIRED_CODE, "This signing request has expired. Please ask for a new one.")
    token = secrets.token_urlsafe(32)
    signer.token_sha256 = _hash(token)
    signer.token_expires_at = None if ttl_seconds is None else now + timedelta(seconds=ttl_seconds)
    signer.updated_at = now
    session.flush()
    events.append(session, t, request, events.TOKEN_ISSUED, signer=signer, now=now,
                  data={"expires_at": iso(signer.token_expires_at)})
    return token


def find_signer_by_token(session, t: Tables, token: str, *, now):
    """The signer a link token belongs to, or None when unknown or past its expiry. Writes nothing."""
    if not token:
        return None
    try:
        digest = _hash(token)
    except UnicodeEncodeError:  # a lone surrogate cannot be a token this library issued
        return None
    signer = session.execute(select(t.signer).where(t.signer.token_sha256 == digest)).scalar_one_or_none()
    if signer is None:
        return None
    if signer.token_expires_at is not None and utc(now) >= signer.token_expires_at:
        return None
    return signer


def find_signer_by_key(session, t: Tables, request_id: str, key: str):
    """The signer of that request whose ``key`` is the app's reference (lowest position if several), or None."""
    if not request_id or not key:
        return None
    return session.execute(
        select(t.signer).where(t.signer.request_id == request_id, t.signer.key == key).order_by(t.signer.position)
    ).scalars().first()
