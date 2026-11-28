"""The emailed one-time code: six digits, hashed with the signer id, short-lived, attempt-limited."""

import hmac
import secrets
from datetime import timedelta

from bond_esign import events
from bond_esign._rows import PENDING, clean, clean_ctx, lock, policy_of, request_of, utc
from bond_esign.errors import CODE_INVALID, CODE_TOO_SOON, NOT_OPEN, TOO_MANY_ATTEMPTS, EsignError
from bond_esign.lifecycle import require_open
from bond_esign.pdf_read import sha256_hex
from bond_esign.types import RequestContext, Tables


def _digest(signer, code: str) -> str:
    return sha256_hex(f"{signer.id}:{code}".encode())


def _active(session, t: Tables, signer, now):
    request = request_of(session, t, signer)
    lock(session, t, request, signer)
    require_open(session, t, request, now)
    if signer.status != PENDING:
        raise EsignError(NOT_OPEN, "This document can no longer be signed.")
    return request, policy_of(request)


def issue_code(session, t: Tables, signer, *, now) -> str:
    """Make a fresh 6-digit code (the app emails it). ``code_too_soon`` inside the resend gap."""
    now = utc(now)
    request, policy = _active(session, t, signer, now)
    if signer.code_sent_at is not None and now < signer.code_sent_at + timedelta(seconds=policy.code_resend_seconds):
        raise EsignError(CODE_TOO_SOON, "A code was just sent. Please wait a moment before asking for another.")
    code = f"{secrets.randbelow(10**6):06d}"
    signer.code_sha256 = _digest(signer, code)
    signer.code_sent_at = now
    signer.code_expires_at = now + timedelta(seconds=policy.code_ttl_seconds)
    signer.code_attempts = 0
    signer.code_verified_at = None
    signer.updated_at = now
    session.flush()
    events.append(session, t, request, events.CODE_SENT, signer=signer, data={}, now=now)
    return code


def verify_code(session, t: Tables, signer, code: str, *, ctx: RequestContext | None, now) -> bool:
    """True when the code is right. A wrong or expired code returns False (and counts an attempt).

    A signer who is already verified (no newer code issued) gets True again, with no new event.
    """
    now = utc(now)
    code, ctx = clean(code, 64) or "", clean_ctx(ctx)
    request, policy = _active(session, t, signer, now)
    if signer.code_verified_at is not None and signer.code_sha256 is None:
        return True  # already verified and no newer code was issued (a double submit): nothing to record
    if signer.code_sha256 is None:
        raise EsignError(CODE_INVALID, "No code is waiting. Please ask for a new code.")
    if signer.code_attempts >= policy.code_max_attempts:
        raise EsignError(TOO_MANY_ATTEMPTS, "Too many wrong codes. Please ask for a new code.")
    expired = signer.code_expires_at is None or now >= signer.code_expires_at
    right = hmac.compare_digest(_digest(signer, (code or "").strip()), signer.code_sha256)
    if expired or not right:
        signer.code_attempts += 1
        signer.updated_at = now
        session.flush()
        events.append(session, t, request, events.CODE_FAILED, signer=signer, ctx=ctx,
                      data={"reason": "expired" if expired else "wrong"}, now=now)
        return False
    signer.code_verified_at = now
    signer.code_sha256 = None
    signer.updated_at = now
    session.flush()
    events.append(session, t, request, events.CODE_VERIFIED, signer=signer, ctx=ctx, data={}, now=now)
    return True
