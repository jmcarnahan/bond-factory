"""`NativeProvider`: the host's `EsignProvider` seam implemented over bond_esign (the adopter's whole adapter)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlencode

import bond_esign as be
from sqlalchemy import select

from .esign_seam import CANNOT_VOID, EsignError

#: lib request status -> the host's words (`open` is `sent` until the signer has opened the page)
STATUS_WORDS = {"open": "sent", "signed": "delivered"}
TOKEN_DAYS = 7


class NativeProvider:
    def __init__(self, session, tables: be.Tables, consent: be.Consent, now: Callable[[], datetime], store, *,
                 name: str = "native") -> None:
        """What the host owns: its session (it commits), tables, consent text, clock (naive UTC), byte store."""
        self.name, self.session, self.t, self.consent, self.now, self.store = name, session, tables, consent, now, store

    def create_envelope(self, *, estimate, pdf: bytes, file_name: str, signer_name: str, signer_email: str,
                        client_user_id: str, email_subject: str) -> str:
        spec = be.SignerSpec(name=signer_name, email=signer_email, key=client_user_id,
                             anchor=be.AnchorRule("Accepted by (customer)"))
        with self._lib_errors():
            request = be.create_request(
                self.session, self.t, pdf=pdf, title=file_name or estimate.title, signers=[spec],
                consent=self.consent, now=self.now(), subject_type="estimate", subject_id=str(estimate.id))
        request.legacy_estimate_id = str(estimate.id)  # the app's own column, written beside the lib's
        self.store.put(f"esign/{request.id}/original.pdf", pdf)
        return request.id

    def recipient_view_url(self, *, envelope_id: str, signer_name: str, signer_email: str, client_user_id: str,
                           return_url: str) -> str:
        request = self._request(envelope_id)
        signer = self.session.execute(select(self.t.signer).where(
            self.t.signer.request_id == request.id, self.t.signer.key == client_user_id)).scalars().first()
        if signer is None:
            raise EsignError(f"no signer {client_user_id!r} on {envelope_id}", code="SIGNER_NOT_FOUND")
        with self._lib_errors():
            token = be.issue_token(self.session, self.t, signer, now=self.now(), ttl_seconds=TOKEN_DAYS * 86400)
        sep = "&" if "?" in return_url else "?"
        return f"{return_url}{sep}{urlencode({'sign': 1, 't': token})}"

    def void(self, envelope_id: str, reason: str) -> None:
        with self._lib_errors():
            be.void(self.session, self.t, self._request(envelope_id), reason=reason, ctx=None, now=self.now())

    def status(self, envelope_id: str) -> str:
        be.expire_due(self.session, self.t, now=self.now())  # the host runs no sweep: an overdue request says so here
        request = self._request(envelope_id)
        if request.status == "open":
            viewed = self.session.execute(select(self.t.event.id).where(
                self.t.event.request_id == request.id, self.t.event.kind == be.VIEWED)).first()
            return "delivered" if viewed else "sent"
        return STATUS_WORDS.get(request.status, request.status)

    def fetch_signed_pdf(self, envelope_id: str) -> bytes:
        request, key = self._request(envelope_id), f"esign/{envelope_id}/signed.pdf"
        if request.status == "signed":  # everyone signed: build, record, store (the host's job worker, inline here)
            with self._lib_errors():
                built = be.build_signed_pdf(self.session, self.t, request,
                                            pdf=self.store.get(f"esign/{envelope_id}/original.pdf"))
                self.store.put(key, built.pdf)
                be.complete(self.session, self.t, request, signed=built, now=self.now())
        elif request.status != "completed":  # only `open` can still complete; the rest never will
            raise EsignError(f"envelope {envelope_id} is {request.status}", retryable=request.status == "open",
                             code=be.errors.NOT_READY if request.status == "open" else request.status)
        stored = self.store.get(key)
        if be.sha256_hex(stored) != request.signed_sha256:  # never serve bytes the record does not vouch for
            raise EsignError(f"stored signed copy of {envelope_id} does not match its record", retryable=False,
                             code="SIGNED_COPY_MISMATCH")
        return stored

    def _request(self, envelope_id: str):
        request = self.session.get(self.t.request, envelope_id)
        if request is None:
            raise EsignError(f"unknown envelope {envelope_id}", code="ENVELOPE_NOT_FOUND")
        return request

    @staticmethod
    def _lib_errors():
        return _LibErrors()


class _LibErrors:
    """The lib's `EsignError` becomes the host's; `already_completed` is the host's `CANNOT_VOID`."""

    def __enter__(self):
        return self

    def __exit__(self, kind, exc, tb):
        if isinstance(exc, be.EsignError):
            code = CANNOT_VOID if exc.code == be.errors.ALREADY_COMPLETED else exc.code
            raise EsignError(exc.message, code=code, retryable=exc.code == be.errors.NOT_READY) from exc
        return False
