"""The host's e-signature provider seam, as the app had it before bond_esign.

`EsignProvider` is the host's contract; two providers sit behind it (a stand-in for the third-party vendor the app
used, and `NativeProvider` over bond_esign). The service functions below are what existing code calls; they are
written against the Protocol only and route by the envelope row's `provider` column.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol


class EsignProvider(Protocol):
    name: str
    def create_envelope(self, *, estimate, pdf: bytes, file_name: str, signer_name: str, signer_email: str,
                        client_user_id: str, email_subject: str) -> str: ...
    def recipient_view_url(self, *, envelope_id: str, signer_name: str, signer_email: str, client_user_id: str,
                           return_url: str) -> str: ...
    def void(self, envelope_id: str, reason: str) -> None: ...
    def fetch_signed_pdf(self, envelope_id: str) -> bytes: ...
    def status(self, envelope_id: str) -> str: ...


class EsignError(Exception):  # the host's own, not the lib's
    def __init__(self, message, *, retryable=False, code=None):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


CANNOT_VOID = "ENVELOPE_CANNOT_VOID_INVALID_STATE"
#: the statuses the host stores; `esign_envelopes.status` holds one of them
STATUSES = ("sent", "delivered", "completed", "declined", "voided", "expired")


def provider_for(envelope, providers: Mapping[str, EsignProvider]) -> EsignProvider:
    """The provider that made this envelope: the row's `provider` column decides, nothing else."""
    try:
        return providers[envelope.provider]
    except KeyError:
        raise EsignError(f"no provider named {envelope.provider!r}", code="UNKNOWN_PROVIDER") from None


def send_for_signature(session, providers, provider: str, estimate, *, pdf: bytes, file_name: str,
                       signer_name: str, signer_email: str, client_user_id: str, now: datetime, envelope_class):
    """Create the envelope at `provider` and record the row (`sent`). Commits."""
    if provider not in providers:
        raise EsignError(f"no provider named {provider!r}", code="UNKNOWN_PROVIDER")
    envelope_id = providers[provider].create_envelope(
        estimate=estimate, pdf=pdf, file_name=file_name, signer_name=signer_name, signer_email=signer_email,
        client_user_id=client_user_id, email_subject=f"Please sign: {file_name}")
    row = envelope_class(id=f"env-{provider}-{envelope_id}", estimate_id=str(estimate.id), provider=provider,
                         envelope_id=envelope_id, status="sent", signer_name=signer_name,
                         signer_email=signer_email, client_user_id=client_user_id, sent_at=now)
    session.add(row)
    session.commit()
    return row


def signing_link(session, providers, envelope, return_url: str) -> str:
    """The signer's link (a native provider issues a token, so this commits)."""
    url = provider_for(envelope, providers).recipient_view_url(
        envelope_id=envelope.envelope_id, signer_name=envelope.signer_name, signer_email=envelope.signer_email,
        client_user_id=envelope.client_user_id, return_url=return_url)
    session.commit()
    return url


def envelope_status(session, providers, envelope, *, now: datetime) -> str:
    """Ask the provider, store the answer on the row (`completed_at` the first time it completes). Commits."""
    status = provider_for(envelope, providers).status(envelope.envelope_id)
    if status != envelope.status:
        envelope.status = status
        if status == "completed" and envelope.completed_at is None:
            envelope.completed_at = now
        session.commit()
    return status


def void_envelope(session, providers, envelope, reason: str) -> None:
    """Void at the provider (it may refuse with `CANNOT_VOID`), then mark the row. Commits."""
    provider_for(envelope, providers).void(envelope.envelope_id, reason)
    envelope.status = "voided"
    session.commit()


def signed_pdf(session, providers, envelope, *, now: datetime) -> bytes:
    """The signed copy; a provider that is not done says so with `EsignError(retryable=True)`."""
    pdf = provider_for(envelope, providers).fetch_signed_pdf(envelope.envelope_id)
    envelope_status(session, providers, envelope, now=now)
    return pdf


def complete_envelope(session, providers, envelope, now: datetime):
    """The app's completion job, written the way it always was: ask `status()`, fetch only when it says completed.

    A job runner retries the `RuntimeError`. Native signing enqueues this from the sign POST; the vendor did from its webhook.
    """
    if envelope.status == "completed":
        return None  # already done: skip
    provider = provider_for(envelope, providers)
    state = provider.status(envelope.envelope_id)
    if state != "completed":
        raise RuntimeError(f"envelope {envelope.envelope_id} is {state}, not completed: trying again later")
    pdf = provider.fetch_signed_pdf(envelope.envelope_id)
    envelope.status = "completed"
    envelope.completed_at = now
    session.commit()
    return pdf


def take_back(session, providers, estimate_id: str, reason: str) -> None:
    """Void every open envelope of the estimate; a provider that refuses with `CANNOT_VOID` is asked once more."""
    from .esign_models import EsignEnvelope  # the host's own table

    rows = session.query(EsignEnvelope).filter(EsignEnvelope.estimate_id == estimate_id,
                                               EsignEnvelope.status.in_(("sent", "delivered"))).all()
    for row in rows:
        try:
            void_envelope(session, providers, row, reason)
        except EsignError as err:
            if err.code != CANNOT_VOID:
                raise
            if provider_for(row, providers).status(row.envelope_id) == "completed":
                raise EsignError("This estimate has already been signed.", code="ALREADY_SIGNED") from err
            raise
