"""The e-signature side of an app that already exists: its own `estimates` and `esign_envelopes` tables (legacy
DDL, mapped here) and the three bond_esign tables attached beside them, with the app's `legacy_estimate_id` on the
request."""

from __future__ import annotations

from bond_esign import EsignEventMixin, EsignRequestMixin, EsignSignerMixin, Tables, default_consent
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from .db import Base


class Estimate(Base):
    __tablename__ = "estimates"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    total = Column(Integer, nullable=False)


class EsignEnvelope(Base):
    """The table the app had with its old vendor: statuses `sent | delivered | completed | declined | voided | expired`."""

    __tablename__ = "esign_envelopes"
    id = Column(String, primary_key=True)
    estimate_id = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    envelope_id = Column(String, nullable=False)
    status = Column(String, nullable=False)
    signer_name = Column(String, nullable=True)
    signer_email = Column(String, nullable=True)
    client_user_id = Column(String, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("provider", "envelope_id", name="uq_esign_envelopes_provider_envelope"),)


class EsignRequest(EsignRequestMixin, Base):
    legacy_estimate_id = Column(String, nullable=True)  # the app's own column; the lib never reads it


class EsignSigner(EsignSignerMixin, Base):
    pass


class EsignEvent(EsignEventMixin, Base):
    pass


TABLES = Tables(request=EsignRequest, signer=EsignSigner, event=EsignEvent)
CONSENT = default_consent(company_name="Example Roofing Co", paper_contact="office@example.com")


class MemoryStore:
    """The host's byte store (two calls); a real app keeps the PDFs in its document storage."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.blobs[key] = data

    def get(self, key: str) -> bytes:
        return self.blobs[key]
