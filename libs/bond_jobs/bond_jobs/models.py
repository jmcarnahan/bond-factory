"""Declarative mixins for the ``background_jobs`` table.

    class Base(DeclarativeBase): ...
    class JobRecord(JobsMixin, Base): ...

The mixin owns the table name and the claim index. A multi-tenant app uses ``TenantJobsMixin`` instead and
adds its own foreign key on ``company_id`` (the mixin has none, so it works with any tenant table).
"""

import uuid

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import declared_attr

from bond_jobs.constants import DEFAULT_MAX_ATTEMPTS, PENDING


def _uuid() -> str:
    return str(uuid.uuid4())


class JobsMixin:
    __tablename__ = "background_jobs"

    @declared_attr.directive
    def __table_args__(cls):
        return (Index("ix_background_jobs_claim", "status", "run_at"),)

    id = Column(String, primary_key=True, default=_uuid)
    job_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    run_at = Column(DateTime, nullable=False, default=func.now())
    status = Column(String, nullable=False, default=PENDING)  # pending | running | done | dead
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=DEFAULT_MAX_ATTEMPTS)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    idempotency_key = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class TenantJobsMixin(JobsMixin):
    """Adds a nullable ``company_id`` tag (no foreign key; ``None`` marks a platform-wide job)."""

    company_id = Column(String, nullable=True, index=True)
