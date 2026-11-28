"""Request lifecycle outside signing: expiry, decline, void, delivery and download records."""

from sqlalchemy import select

from bond_esign import events
from bond_esign._rows import (
    COMPLETED,
    DECLINED,
    EXPIRED,
    OPEN,
    PENDING,
    VOIDED,
    clean,
    clean_ctx,
    lock,
    request_of,
    utc,
)
from bond_esign.errors import ALREADY_COMPLETED, NOT_OPEN, EsignError
from bond_esign.errors import EXPIRED as EXPIRED_CODE
from bond_esign.types import RequestContext, Tables


def expire_if_due(session, t: Tables, request, now) -> bool:
    """Flip an open request that is past ``expires_at`` to ``expired`` (with an event). True when it flipped.

    The row lock is taken (and the row reloaded) before the check is made again, so a request another
    transaction has just signed, declined or expired is left alone.
    """
    now = utc(now)
    if request.status != OPEN or request.expires_at is None or now < request.expires_at:
        return False  # cheap look at what is already loaded: nothing to lock
    lock(session, t, request)
    if request.status == OPEN and request.expires_at is not None and now >= request.expires_at:
        request.status = EXPIRED
        request.updated_at = now
        events.append(session, t, request, events.EXPIRED, data={}, now=now)
        return True
    return False


def require_open(session, t: Tables, request, now) -> None:
    """Raise ``expired`` or ``not_open`` unless the request can still take signatures."""
    if expire_if_due(session, t, request, now) or request.status == EXPIRED:
        raise EsignError(EXPIRED_CODE, "This signing request has expired. Please ask for a new one.")
    if request.status != OPEN:
        raise EsignError(NOT_OPEN, "This document can no longer be signed.")


def expire_due(session, t: Tables, *, now) -> int:
    """Flip every open request past its ``expires_at``. Returns how many flipped."""
    now = utc(now)
    due = session.execute(
        select(t.request).where(t.request.status == OPEN, t.request.expires_at.is_not(None),
                                t.request.expires_at <= now)
    ).scalars().all()
    return sum(1 for request in due if expire_if_due(session, t, request, now))


def decline(session, t: Tables, signer, *, reason: str | None, ctx: RequestContext | None, now):
    """The signer refuses: signer and request become ``declined``. Returns the request."""
    now = utc(now)
    reason, ctx = clean(reason, 2000), clean_ctx(ctx)  # all input is checked before any state changes
    request = request_of(session, t, signer)
    lock(session, t, request, signer)
    require_open(session, t, request, now)
    if signer.status != PENDING:
        raise EsignError(NOT_OPEN, "This document can no longer be signed.")
    signer.status = DECLINED
    signer.decline_reason = reason
    signer.updated_at = now
    request.status = DECLINED
    request.declined_at = now
    request.updated_at = now
    events.append(session, t, request, events.DECLINED, signer=signer, ctx=ctx, data={"reason": reason}, now=now)
    return request


def void(session, t: Tables, request, *, reason: str, ctx: RequestContext | None, now):
    """Cancel a request. Refused once completed; a second call on a voided request changes nothing."""
    now = utc(now)
    reason, ctx = clean(reason, 2000), clean_ctx(ctx)  # all input is checked before any state changes
    lock(session, t, request)
    if request.status == COMPLETED:
        raise EsignError(ALREADY_COMPLETED, "This document is already signed and completed, so it cannot be voided.")
    if request.status == VOIDED:
        return request
    request.status = VOIDED
    request.voided_at = now
    request.void_reason = reason
    request.updated_at = now
    events.append(session, t, request, events.VOIDED, ctx=ctx, data={"reason": reason}, now=now)
    return request


def record_delivery(session, t: Tables, request, *, channel: str, reference: str | None = None, signer=None,
                    ctx: RequestContext | None = None, now) -> None:
    """Record that the signed copy was handed to the signer (the app sends it; the library only records)."""
    events.append(session, t, request, events.COPY_DELIVERED, signer=signer, ctx=ctx,
                  data={"channel": clean(channel, 200), "reference": clean(reference, 500)}, now=now)


def record_download(session, t: Tables, request, *, signer=None, ctx: RequestContext | None = None, now) -> None:
    events.append(session, t, request, events.DOWNLOADED, signer=signer, ctx=ctx, data={}, now=now)
