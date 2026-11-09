"""Declarative mixin for the ``oauth_connections`` table.

    class OAuthConnection(ConnectionsMixin, Base): ...

``user_id`` is NULL for a shared (office) connection. Its foreign key points at ``user_fk_target`` (default
``users.id``); a subclass sets ``user_fk_target = None`` for no key, or another ``table.column``.
One live row (``revoked_at`` NULL) per (user_id, provider, connection_name) is kept by ``service.complete`` and
backed by the partial unique index ``uq_oauth_connections_live``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import declared_attr


def _uuid() -> str:
    return str(uuid.uuid4())


class ConnectionsMixin:
    __tablename__ = "oauth_connections"
    user_fk_target: str | None = "users.id"

    @declared_attr.directive
    def __table_args__(cls):
        live = text("revoked_at IS NULL")
        return (
            Index("ix_oauth_connections_owner", "user_id", "provider", "connection_name"),
            # One live row per (owner, provider, connection_name); a shared connection has user_id NULL.
            Index("uq_oauth_connections_live", text("coalesce(user_id, '')"), "provider", "connection_name",
                  unique=True, sqlite_where=live, postgresql_where=live),
        )

    @declared_attr
    def user_id(cls):
        args = [String] + ([ForeignKey(cls.user_fk_target)] if cls.user_fk_target else [])
        return Column(*args, nullable=True, index=True)

    id = Column(String, primary_key=True, default=_uuid)
    provider = Column(String, nullable=False)
    connection_name = Column(String, nullable=False)
    account_email = Column(String, nullable=False)
    scopes = Column(String, nullable=True)  # space-separated, as granted
    access_token_enc = Column(Text, nullable=True)
    refresh_token_enc = Column(Text, nullable=False)
    token_type = Column(String, default="Bearer")
    expires_at = Column(DateTime, nullable=True)
    provider_metadata = Column(Text, nullable=True)  # JSON
    connected_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    revoked_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
