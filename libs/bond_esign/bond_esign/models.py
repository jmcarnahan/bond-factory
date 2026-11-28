"""Declarative mixins for the ``esign_requests``, ``esign_signers`` and ``esign_events`` tables.

    class Base(DeclarativeBase): ...
    class EsignRequest(EsignRequestMixin, Base): ...      # or TenantEsignRequestMixin
    class EsignSigner(EsignSignerMixin, Base): ...
    class EsignEvent(EsignEventMixin, Base): ...
    T = Tables(request=EsignRequest, signer=EsignSigner, event=EsignEvent)

The mixins own the table names, the foreign keys (to ``esign_requests.id``) and the constraints. The event
table is append-only: the library never updates or deletes a row of it. All datetimes are naive UTC.
"""

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declared_attr


def _uuid() -> str:
    return str(uuid.uuid4())


class EsignRequestMixin:
    __tablename__ = "esign_requests"

    @declared_attr.directive
    def __table_args__(cls):
        return (Index("ix_esign_requests_subject", "subject_type", "subject_id"),)

    id = Column(String, primary_key=True, default=_uuid)
    status = Column(String, nullable=False)  # open | signed | completed | declined | voided | expired
    title = Column(String, nullable=False)
    subject_type = Column(String, nullable=True)
    subject_id = Column(String, nullable=True)
    document_sha256 = Column(String(64), nullable=False)
    document_bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False)
    consent_version = Column(String, nullable=False)
    consent_language = Column(String, nullable=False)
    consent_sha256 = Column(String(64), nullable=False)
    consent_text = Column(Text, nullable=False)
    policy = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    signed_sha256 = Column(String(64), nullable=True)
    sealed = Column(Boolean, nullable=False, default=False)
    timestamped = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    declined_at = Column(DateTime, nullable=True)
    void_reason = Column(Text, nullable=True)
    meta = Column(JSON, nullable=False, default=dict)  # app-owned; the library never reads it
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class TenantEsignRequestMixin(EsignRequestMixin):
    """Adds a nullable, indexed ``company_id`` tag (no foreign key, so it works with any tenant table)."""

    company_id = Column(String, nullable=True, index=True)


class EsignSignerMixin:
    __tablename__ = "esign_signers"

    @declared_attr.directive
    def __table_args__(cls):
        return (UniqueConstraint("request_id", "position", name="uq_esign_signers_request_position"),)

    @declared_attr
    def request_id(cls):
        return Column(String, ForeignKey("esign_requests.id", ondelete="CASCADE"), nullable=False, index=True)

    id = Column(String, primary_key=True, default=_uuid)
    position = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    role = Column(String, nullable=False)
    key = Column(String, nullable=True)
    status = Column(String, nullable=False)  # pending | signed | declined
    placement = Column(JSON, nullable=True)
    date_placement = Column(JSON, nullable=True)
    token_sha256 = Column(String(64), nullable=True, unique=True)  # only the hash of the link token
    token_expires_at = Column(DateTime, nullable=True)
    code_sha256 = Column(String(64), nullable=True)  # salted with the signer id
    code_expires_at = Column(DateTime, nullable=True)
    code_sent_at = Column(DateTime, nullable=True)
    code_verified_at = Column(DateTime, nullable=True)
    code_attempts = Column(Integer, nullable=False, default=0)
    method = Column(String, nullable=True)  # link | app_link | email_code | in_person, set at signing
    witness = Column(String, nullable=True)
    signature_kind = Column(String, nullable=True)  # typed | drawn
    typed_name = Column(String, nullable=True)
    signature_png = Column(LargeBinary, nullable=True)
    signature_sha256 = Column(String(64), nullable=True)
    signed_at = Column(DateTime, nullable=True)
    ip = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    decline_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class EsignEventMixin:
    __tablename__ = "esign_events"

    @declared_attr.directive
    def __table_args__(cls):
        return (UniqueConstraint("request_id", "seq", name="uq_esign_events_request_seq"),)

    @declared_attr
    def request_id(cls):
        return Column(String, ForeignKey("esign_requests.id", ondelete="CASCADE"), nullable=False)

    id = Column(String, primary_key=True, default=_uuid)
    seq = Column(Integer, nullable=False)
    signer_id = Column(String, nullable=True)
    kind = Column(String, nullable=False)
    at = Column(DateTime, nullable=False)
    ip = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    actor = Column(String, nullable=True)
    data = Column(JSON, nullable=False, default=dict)
    prev_hash = Column(String(64), nullable=False)
    row_hash = Column(String(64), nullable=False)
