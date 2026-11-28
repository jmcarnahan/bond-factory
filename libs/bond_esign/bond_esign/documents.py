"""The signed PDF: gather what the rows say (``build_signed_pdf``), then record it (``complete``)."""

import unicodedata
from datetime import UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from bond_esign import build, events
from bond_esign._rows import COMPLETED, SIGNED, lock, utc
from bond_esign.errors import DOCUMENT_MISMATCH, EVIDENCE_MISMATCH, HASH_CONFLICT, NOT_READY, EsignError
from bond_esign.labels import CertificateLabels
from bond_esign.pdf_read import page_count, sha256_hex
from bond_esign.types import (
    Brand,
    CertificateData,
    CertificateEvent,
    CertificateSigner,
    Placement,
    SignedDocument,
    Stamp,
    Tables,
)
from bond_esign.verify import verify_evidence


def _signers(session, t: Tables, request) -> list:
    return list(session.execute(
        select(t.signer).where(t.signer.request_id == request.id).order_by(t.signer.position)
    ).scalars())


def _stamp(signer, labels: CertificateLabels, zone: ZoneInfo) -> Stamp | None:
    if signer.status != SIGNED or not signer.placement:
        return None
    local = signer.signed_at.replace(tzinfo=UTC).astimezone(zone).date()
    date_text = labels.format_date(local)
    drawn = signer.signature_kind == "drawn" and signer.signature_png
    name = signer.name
    if len(name) > 40:  # the certificate keeps it whole
        cut = name[:40]
        while cut and (unicodedata.combining(cut[-1]) or cut[-1] == " "):
            cut = cut[:-1]  # never end on a stranded combining mark or a space
        name = cut + "..."
    return Stamp(
        placement=Placement(**signer.placement),
        png=signer.signature_png if drawn else None,
        typed_name=None if drawn else signer.typed_name,
        caption=labels.stamp_caption.format(name=name, date=date_text, ref=signer.id[:8]),
        date_text=date_text if signer.date_placement else None,
        date_placement=Placement(**signer.date_placement) if signer.date_placement else None,
    )


_DEFAULT_LABELS = CertificateLabels()


def _detail(event) -> str | None:
    """Which document a ``downloaded`` event was about; an old event without it reads as the signed copy."""
    if event.kind != events.DOWNLOADED:
        return None
    return (event.data or {}).get("document")


def build_signed_pdf(session, t: Tables, request, *, pdf: bytes, labels: CertificateLabels = _DEFAULT_LABELS,
                     brand: Brand | None = None, zone: str = "UTC", sealer=None) -> SignedDocument:
    """Stamp the signatures, add the certificate pages, optionally seal. Writes no event, changes no row.

    The certificate timeline and its chain head use the events up to and including the last ``signed`` event
    (the one that made the request signed), nothing after it, so an event recorded between the last signature
    and ``complete`` (a download of the original, a reminder) never changes the bytes of a rebuild.
    """
    if request.status not in (SIGNED, COMPLETED):
        raise EsignError(NOT_READY, "This document is not fully signed yet.")
    if not verify_evidence(session, t, request).ok:  # a tampered row must never reach a certificate
        raise EsignError(EVIDENCE_MISMATCH, "This signing record failed its integrity check.")
    if sha256_hex(pdf) != request.document_sha256:
        raise EsignError(DOCUMENT_MISMATCH, "The document changed after this signing request was made.")
    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown time zone {zone!r}") from exc
    signers = _signers(session, t, request)
    names = {s.id: s.name for s in signers}
    rows = events.chain(session, t, request)
    last = max((e.seq for e in rows if e.kind == events.SIGNED), default=None)
    if last is not None:  # a rebuild after complete() must see what the first build saw
        rows = [e for e in rows if e.seq <= last]
    certificate = CertificateData(
        request_id=request.id, title=request.title, document_sha256=request.document_sha256,
        page_count=request.page_count, consent_version=request.consent_version,
        consent_language=request.consent_language, consent_sha256=request.consent_sha256,
        consent_text=request.consent_text,
        signers=tuple(
            CertificateSigner(
                ref=s.id[:8], name=s.name, email=s.email, role=s.role, status=s.status, method=s.method,
                witness=s.witness, signed_at=s.signed_at, ip=s.ip, user_agent=s.user_agent,
                signature_kind=s.signature_kind, typed_name=s.typed_name, signature_png=s.signature_png,
                signature_sha256=s.signature_sha256,
            )
            for s in signers
        ),
        events=tuple(CertificateEvent(e.seq, e.at, e.kind, names.get(e.signer_id), _detail(e)) for e in rows),
        chain_head=rows[-1].row_hash if rows else events.ZERO_HASH, zone=zone,
    )
    stamps = [s for s in (_stamp(signer, labels, tz) for signer in signers) if s is not None]
    return build.compose(pdf, title=request.title, stamps=stamps, certificate=certificate, labels=labels,
                         brand=brand, sealer=sealer)


def complete(session, t: Tables, request, *, signed: SignedDocument, now):
    """Record the built PDF: ``signed`` becomes ``completed``. The same hash again is a no-op.

    ``signed`` must be what ``build_signed_pdf`` returned: a hash or page count that does not match its bytes
    is a programming error (``ValueError``).
    """
    now = utc(now)
    if sha256_hex(signed.pdf) != signed.sha256:
        raise ValueError("signed.sha256 is not the sha256 of signed.pdf")
    try:
        pages = page_count(signed.pdf)
    except EsignError as exc:
        raise ValueError("signed.pdf is not a readable PDF") from exc
    if pages != signed.pages:
        raise ValueError(f"signed.pages is {signed.pages} but signed.pdf has {pages} pages")
    lock(session, t, request)
    if request.status == COMPLETED:
        if request.signed_sha256 == signed.sha256:
            return request
        raise EsignError(HASH_CONFLICT, "A different signed copy was already recorded for this document.")
    if request.status != SIGNED:
        raise EsignError(NOT_READY, "This document is not fully signed yet.")
    request.status = COMPLETED
    request.signed_sha256 = signed.sha256
    request.sealed = bool(signed.sealed)
    request.timestamped = bool(signed.timestamped)
    request.completed_at = now
    request.updated_at = now
    events.append(session, t, request, events.DOCUMENT_BUILT, now=now, data={
        "sha256": signed.sha256, "pages": signed.pages, "sealed": bool(signed.sealed),
        "timestamped": bool(signed.timestamped), "timestamp_url": signed.timestamp_url,
    })
    events.append(session, t, request, events.COMPLETED, now=now, data={"sha256": signed.sha256})
    return request
