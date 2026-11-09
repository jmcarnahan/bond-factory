"""Documents and the download grants that share them."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from bond_storage import GrantsMixin
from sqlalchemy import Column, DateTime, ForeignKeyConstraint, String

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Document(Base):
    """A stored file. Satisfies the storage lib's ``DocumentLike``."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=_uuid)
    storage_key = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    kind = Column(String, nullable=False, default="file")
    owner_user_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=_now)

    def public(self) -> dict:
        return {"id": self.id, "filename": self.filename, "content_type": self.content_type, "kind": self.kind,
                "owner_user_id": self.owner_user_id,
                "created_at": self.created_at.isoformat(timespec="seconds") + "Z" if self.created_at else None}


class DownloadGrant(GrantsMixin, Base):
    __table_args__ = (ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),)
