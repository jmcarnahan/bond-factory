"""What the signing page needs (``signing_view``) and what a signature does (``sign``)."""

from sqlalchemy import func, select

from bond_esign import events
from bond_esign._rows import (
    EXPIRED,
    METHODS,
    OPEN,
    PENDING,
    SIGNED,
    clean,
    clean_ctx,
    lock,
    policy_of,
    request_of,
    utc,
)
from bond_esign.errors import (
    CODE_REQUIRED,
    CONSENT_REQUIRED,
    CONSENT_STALE,
    DOCUMENT_MISMATCH,
    DRAWN_NOT_ALLOWED,
    IN_PERSON_NEEDS_ACTOR,
    NOT_OPEN,
    SIGNATURE_REQUIRED,
    TYPED_NOT_ALLOWED,
    EsignError,
)
from bond_esign.errors import (
    EXPIRED as EXPIRED_CODE,
)
from bond_esign.lifecycle import expire_if_due, require_open
from bond_esign.pdf_read import sha256_hex
from bond_esign.signature_image import check_drawn_name, check_typed, normalise_png
from bond_esign.types import Consent, RequestContext, SigningView, SignOutcome, Tables


def _consent_of(request) -> Consent:
    return Consent(request.consent_version, request.consent_language, request.consent_text)


def signing_view(session, t: Tables, signer, *, ctx: RequestContext | None, now,
                 record_view: bool = True) -> SigningView:
    """What the page shows. Records ``viewed`` (at most once per ``view_event_gap_seconds`` per signer).

    ``record_view=False`` writes nothing (link previews, HEAD requests)."""
    now = utc(now)
    request = request_of(session, t, signer)
    expire_if_due(session, t, request, now)
    policy = policy_of(request)
    reason = None
    if request.status == EXPIRED:
        reason = EXPIRED_CODE
    elif request.status != OPEN or signer.status != PENDING:
        reason = NOT_OPEN
    can_sign = reason is None
    if can_sign and record_view:
        last = session.execute(
            select(func.max(t.event.at)).where(
                t.event.request_id == request.id, t.event.signer_id == signer.id, t.event.kind == events.VIEWED
            )
        ).scalar()
        if last is None or (now - utc(last)).total_seconds() >= policy.view_event_gap_seconds:
            events.append(session, t, request, events.VIEWED, signer=signer, ctx=ctx, data={}, now=now)
    return SigningView(
        request_status=request.status, signer_status=signer.status, can_sign=can_sign, reason=reason,
        consent=_consent_of(request), needs_code=policy.require_email_code,
        code_verified=signer.code_verified_at is not None, allow_typed=policy.allow_typed,
        allow_drawn=policy.allow_drawn, signer_name=signer.name, title=request.title,
    )


def _signature(policy, typed_name, drawn_png):
    """(kind, png, typed_name, signature_sha256) for what the signer submitted, or the error to show."""
    typed = (clean(typed_name, 1000) or "").strip()  # controls out; an over-long name is refused by check_typed
    if drawn_png:
        if not policy.allow_drawn:
            raise EsignError(DRAWN_NOT_ALLOWED, "Drawn signatures are not accepted for this document. Please type your name.")
        png = normalise_png(drawn_png, max_bytes=policy.max_signature_bytes)
        return "drawn", png, (check_drawn_name(typed) if typed else None), sha256_hex(png)
    if typed:
        if not policy.allow_typed:
            raise EsignError(TYPED_NOT_ALLOWED, "Typed signatures are not accepted for this document. Please draw your signature.")
        name = check_typed(typed, policy)
        return "typed", None, name, sha256_hex(name.encode("utf-8"))
    raise EsignError(SIGNATURE_REQUIRED, "Please type your name or draw your signature to sign.")


def all_signed(session, t: Tables, request) -> bool:
    pending = session.execute(
        select(func.count()).select_from(t.signer).where(t.signer.request_id == request.id, t.signer.status != SIGNED)
    ).scalar()
    return pending == 0


def sign(session, t: Tables, signer, *, pdf: bytes, consent_version: str, consent_accepted: bool,
         typed_name: str | None, drawn_png: bytes | None, ctx: RequestContext | None, now,
         method: str = "link") -> SignOutcome:
    """Record one signer's signature. Flushes, never commits. A second call for a signed signer is a replay."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; use one of {METHODS}")
    now = utc(now)
    ctx = clean_ctx(ctx)
    request = request_of(session, t, signer)
    lock(session, t, request, signer)
    if signer.status == SIGNED:
        return SignOutcome(request, signer, all_signed(session, t, request), replay=True)
    require_open(session, t, request, now)
    if signer.status != PENDING:
        raise EsignError(NOT_OPEN, "This document can no longer be signed.")
    policy = policy_of(request)
    if sha256_hex(pdf) != request.document_sha256:
        raise EsignError(DOCUMENT_MISMATCH, "The document changed after this signing request was made.")
    if not consent_accepted:
        raise EsignError(CONSENT_REQUIRED, "Please tick the box to agree to sign electronically.")
    if consent_version != request.consent_version:
        raise EsignError(CONSENT_STALE, "The agreement text changed. Please reload the page and read it again.")
    needs_code = method == "email_code" or (policy.require_email_code and method != "in_person")
    if needs_code and signer.code_verified_at is None:
        raise EsignError(CODE_REQUIRED, "Please enter the code we emailed you before signing.")
    if method == "in_person" and not ctx.actor:
        raise EsignError(IN_PERSON_NEEDS_ACTOR, "A staff member must be signed in to record an in-person signature.")
    kind, png, typed, signature_sha = _signature(policy, typed_name, drawn_png)

    signer.status = SIGNED
    signer.method = "email_code" if needs_code else method
    signer.witness = ctx.actor if method == "in_person" else None
    signer.signature_kind, signer.signature_png, signer.typed_name = kind, png, typed
    signer.signature_sha256 = signature_sha
    signer.signed_at, signer.ip, signer.user_agent, signer.updated_at = now, ctx.ip, ctx.user_agent, now
    session.flush()
    events.append(session, t, request, events.CONSENT_GIVEN, signer=signer, ctx=ctx, now=now, data={
        "version": request.consent_version, "language": request.consent_language,
        "sha256": request.consent_sha256,
    })
    events.append(session, t, request, events.SIGNED, signer=signer, ctx=ctx, now=now, data={
        "kind": kind, "signature_sha256": signature_sha, "method": signer.method, "typed_name": typed,
        "name": signer.name,
    })
    done = all_signed(session, t, request)
    if done:
        request.status = SIGNED
        request.updated_at = now
        session.flush()
    return SignOutcome(request, signer, done, replay=False)
