"""Creating a request. The other service functions live beside it and are re-exported here.

signing.py: signing_view, sign. lifecycle.py: decline, void, expire_due, record_*. tokens.py, codes.py.
documents.py: build_signed_pdf, complete. evidence_export.py: evidence.
"""

import dataclasses
import hashlib
from collections.abc import Sequence
from typing import Any

from bond_esign import _validate, anchor, events
from bond_esign._rows import OPEN, clean, policy_of, utc
from bond_esign.codes import issue_code, verify_code
from bond_esign.documents import build_signed_pdf, complete
from bond_esign.errors import INVALID_PDF, TOO_MANY_SIGNERS, EsignError
from bond_esign.evidence_export import evidence
from bond_esign.lifecycle import decline, expire_due, record_delivery, record_download, record_sent, void
from bond_esign.pdf_read import page_count, sha256_hex
from bond_esign.signing import sign, signing_view
from bond_esign.tokens import find_signer_by_key, find_signer_by_token, issue_token
from bond_esign.types import Consent, Placement, Policy, RequestContext, SignerSpec, Tables

__all__ = [
    "build_signed_pdf", "complete", "create_request", "decline", "evidence", "expire_due", "find_signer_by_key",
    "find_signer_by_token", "issue_code", "issue_token", "policy_of", "record_delivery", "record_download", "record_sent", "sign", "signing_view",
    "verify_code", "void",
]

_EPS = 1e-6
DEFAULT_POLICY = Policy()


def _page(page: int, pages: int) -> int:
    """A positive 1-based page number; negative counts from the end. ValueError when off the document."""
    resolved = page if page > 0 else pages + page + 1 if page < 0 else 0
    if not 1 <= resolved <= pages:
        raise ValueError(f"placement page {page} is outside a {pages}-page document")
    return resolved


def _placement(p: Placement, pages: int, *, clamp: bool = False) -> dict:
    x, y, w, h = p.x, p.y, p.w, p.h
    if clamp:  # a box found from an anchor may poke over the page edge: pull it back in
        x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
        w, h = min(w, 1.0 - x), min(h, 1.0 - y)
    if not (0 <= x <= 1 and 0 <= y <= 1 and w > 0 and h > 0 and x + w <= 1 + _EPS and y + h <= 1 + _EPS):
        raise ValueError(f"placement {p} is outside the page (fractions of the page, 0..1)")
    return {"page": _page(p.page, pages), "x": x, "y": y, "w": w, "h": h}


def _resolve_date(spec: SignerSpec, pdf: bytes, pages: int, missing: list[str]) -> dict | None:
    if spec.date_placement is not None:
        return _placement(spec.date_placement, pages)
    if spec.date_anchor is None:
        return None
    found = anchor.find_anchor(pdf, spec.date_anchor)
    if found is not None:
        try:
            return _placement(found, pages, clamp=True)
        except ValueError:
            pass
    missing.append(spec.date_anchor.text)
    return None


def _resolve(spec: SignerSpec, pdf: bytes, pages: int, missing: list[str]) -> dict | None:
    if spec.placement is not None:
        return _placement(spec.placement, pages)
    if spec.anchor is None:
        return None
    found = anchor.find_anchor(pdf, spec.anchor)  # through the module so tests can replace it
    if found is not None:
        try:
            return _placement(found, pages, clamp=True)
        except ValueError:
            pass
    missing.append(spec.anchor.text)
    return None


def create_request(session, t: Tables, *, pdf: bytes, title: str, signers: Sequence[SignerSpec], consent: Consent,
                   now, policy: Policy = DEFAULT_POLICY, subject_type: str | None = None,
                   subject_id: str | None = None, expires_at=None, company_id: str | None = None,
                   meta: dict | None = None, ctx: RequestContext | None = None) -> Any:
    """Open a signing request for ``pdf``. Flushes, never commits. Returns the request row."""
    if not signers:
        raise ValueError("a signing request needs at least one signer")
    _validate.check_request(title=title, consent=consent, signers=signers, policy=policy, now=utc(now),
                            expires_at=None if expires_at is None else utc(expires_at))
    if company_id is not None and not hasattr(t.request, "company_id"):
        raise ValueError("company_id given, but the request table was not built from TenantEsignRequestMixin")
    if len(pdf) > policy.max_pdf_bytes:
        raise EsignError(INVALID_PDF, "This PDF is too large to send for signing.")
    pages = page_count(pdf)
    if len(signers) > policy.max_signers:
        raise EsignError(TOO_MANY_SIGNERS, f"A document can have at most {policy.max_signers} signers.")
    now = utc(now)
    missing: list[str] = []
    resolved = []
    for spec in signers:
        box = _resolve(spec, pdf, pages, missing)
        date_box = _resolve_date(spec, pdf, pages, missing)
        if date_box is not None and (box is None or date_box["page"] != box["page"]):
            if spec.date_placement is not None and box is not None:
                raise ValueError("date_placement must be on the same page as the signature placement")
            if spec.date_anchor is not None and spec.date_placement is None:
                missing.append(spec.date_anchor.text)
            date_box = None  # the date is drawn on the signature's page, so a box elsewhere cannot be used
        resolved.append((spec, box, date_box))
    request = t.request(
        status=OPEN, title=clean(title, 500), subject_type=subject_type, subject_id=subject_id,
        document_sha256=sha256_hex(pdf), document_bytes=len(pdf), page_count=pages,
        consent_version=consent.version, consent_language=consent.language,
        consent_sha256=hashlib.sha256(consent.text.encode("utf-8")).hexdigest(), consent_text=consent.text,
        policy=dataclasses.asdict(policy), expires_at=None if expires_at is None else utc(expires_at),
        sealed=False, timestamped=False, meta=dict(meta or {}), created_at=now, updated_at=now,
    )
    if company_id is not None:
        request.company_id = company_id
    session.add(request)
    session.flush()
    rows = []
    for position, (spec, placement, date_placement) in enumerate(resolved):
        row = t.signer(
            request_id=request.id, position=position, name=clean(spec.name, 500), email=clean(spec.email, 500),
            role=clean(spec.role, 500), key=clean(spec.key, 500), status="pending", placement=placement, date_placement=date_placement,
            code_attempts=0, created_at=now, updated_at=now,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    data = {  # everything verify_evidence cross-checks against the rows
        "document_sha256": request.document_sha256, "title": request.title,
        "consent_version": request.consent_version, "consent_sha256": request.consent_sha256,
        "signers": [
            {"id": r.id, "position": r.position, "name": r.name, "email": r.email, "role": r.role, "key": r.key}
            for r in rows
        ],
    }
    if missing:
        data["anchor_missing"] = missing
    events.append(session, t, request, events.CREATED, ctx=ctx, data=data, now=now)
    return request
