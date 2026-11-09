"""Declarative mixin for the ``auth_sessions`` table: one row per refresh token.

    class AuthSession(SessionsMixin, Base): ...

``user_id`` points at ``user_fk_target`` (default ``users.id``); a subclass sets ``user_fk_target = None`` for no
key. Rows of one sign-in share ``family_id``: every rotation adds a child row and marks the parent rotated.
Datetimes are naive UTC, as in ``ConnectionsMixin``. Only ``sha256`` hashes of the tokens are stored.
Libs ship no migrations: the app's own migration creates the table, and its schema test inspects the columns.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import declared_attr


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class SessionsMixin:
    __tablename__ = "auth_sessions"
    user_fk_target: str | None = "users.id"

    @declared_attr.directive
    def __table_args__(cls):
        return (
            Index("uq_auth_sessions_token_hash", "token_hash", unique=True),
            Index("ix_auth_sessions_family_id", "family_id"),
            Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),
            Index("ix_auth_sessions_expires_at", "expires_at"),
        )

    @declared_attr
    def user_id(cls):
        args = [String] + ([ForeignKey(cls.user_fk_target)] if cls.user_fk_target else [])
        return Column(*args, nullable=False)

    id = Column(String, primary_key=True, default=_uuid)
    family_id = Column(String, nullable=False)
    token_hash = Column(String(43), nullable=False)  # sha256, base64url, no padding
    parent_id = Column(String, nullable=True)
    provider = Column(String(16), nullable=False)  # google | microsoft | password | demo
    auth_time = Column(DateTime, nullable=False)  # the IdP sign-in instant, copied to every child
    family_expires_at = Column(DateTime, nullable=True)  # auth_time + refresh_max_days; NULL = no cap
    expires_at = Column(DateTime, nullable=False)  # now + refresh_ttl_days, never past family_expires_at
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    last_used_at = Column(DateTime, nullable=True)  # set when this token is rotated (claimed)
    rotated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(String(16), nullable=True)  # reuse | logout | admin | limit | signout_all | retry
    device_label = Column(String(80), nullable=True)
    rotation_id = Column(String(64), nullable=True)  # the client's random id for the refresh that made this row
    last_probed_at = Column(DateTime, nullable=True)  # last IdP liveness probe of the family, copied forward
