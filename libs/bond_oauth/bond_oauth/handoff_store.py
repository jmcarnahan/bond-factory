"""Database-backed one-time hand-off codes (table ``oauth_handoffs``).

A phone app that finished a browser flow gets a short-lived ``code`` and trades it for the result. The row holds the
sealed payload, never a token in a URL. Single use is one ``UPDATE ... WHERE used_at IS NULL``, so it holds across
processes and restarts. A code is bound to the device: the app sends ``sha256`` of a 32-byte secret when it starts
and presents the secret at redeem; a wrong secret burns the code.

    class OAuthHandoff(HandoffsMixin, Base): ...
    store = HandoffStore(OAuthHandoff, cipher)
    code = store.issue(session, purpose="signin", provider="google", payload={...}, device_hash=h, attempt_id=a)
    payload = store.redeem(session, code=code, device_secret=secret, purpose="signin")
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Column, DateTime, Index, String, Text, delete, select, update
from sqlalchemy.orm import Session, declared_attr

from bond_oauth.cipher import TokenCipher
from bond_oauth.errors import OAuthError

HANDOFF_TTL_SECONDS = 120
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ATTEMPT = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _uuid() -> str:
    return str(uuid.uuid4())


def _naive_utc(epoch: float | None) -> datetime:
    moment = datetime.now(UTC) if epoch is None else datetime.fromtimestamp(epoch, UTC)
    return moment.replace(tzinfo=None)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _invalid(message: str = "The hand-off code is not valid") -> OAuthError:
    return OAuthError("invalid_handoff", message)


class HandoffsMixin:
    """Declarative mixin for ``oauth_handoffs`` (no migration here: the app's Alembic owns it)."""

    __tablename__ = "oauth_handoffs"

    @declared_attr.directive
    def __table_args__(cls):
        return (Index("ix_oauth_handoffs_expires_at", "expires_at"),)

    id = Column(String, primary_key=True, default=_uuid)
    code_hash = Column(String(64), nullable=False, unique=True)  # sha256 hex of the code
    device_hash = Column(String(64), nullable=False)  # sha256 hex of the device secret
    purpose = Column(String(16), nullable=False)  # "signin" | "connect"
    provider = Column(String, nullable=False)
    attempt_id = Column(String(64), nullable=True)
    payload_enc = Column(Text, nullable=False)  # cipher-sealed JSON
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)


class HandoffStore:
    def __init__(self, model: Any, cipher: TokenCipher) -> None:
        self._model, self._cipher = model, cipher

    def issue(self, session: Session, *, purpose: str, provider: str, payload: dict, device_hash: str,
              attempt_id: str | None, ttl: int = HANDOFF_TTL_SECONDS, now: float | None = None) -> str:
        """Store a sealed payload and return the one-time code (only its hash is kept). ``device_hash`` must be 64
        lowercase hex; a bad one is ``OAuthError("invalid_request")``. Commits."""
        if not _HEX64.fullmatch(device_hash or ""):
            raise OAuthError("invalid_request", "The device hash is not valid")
        if attempt_id is not None and not _ATTEMPT.fullmatch(attempt_id):
            raise OAuthError("invalid_request", "The attempt id is not valid")
        code = secrets.token_urlsafe(32)
        stamp = _naive_utc(now)
        session.add(self._model(
            code_hash=_sha256_hex(code), device_hash=device_hash, purpose=purpose, provider=provider,
            attempt_id=attempt_id, payload_enc=self._cipher.encrypt_state(json.dumps(payload, separators=(",", ":"))),
            created_at=stamp, expires_at=stamp + timedelta(seconds=ttl)))
        session.commit()
        return code

    def redeem(self, session: Session, *, code: str, device_secret: str, purpose: str,
               now: float | None = None) -> dict:
        """The payload, once. ONE statement claims the row (``used_at`` NULL and not expired); any other outcome
        (unknown, used, expired, wrong device secret, wrong purpose) is ``OAuthError("invalid_handoff")``. The
        claim is committed first, so a wrong secret or purpose has already burned the code."""
        model, stamp = self._model, _naive_utc(now)
        code_hash = _sha256_hex(code or "")
        claimed = session.execute(update(model).where(
            model.code_hash == code_hash, model.used_at.is_(None), model.expires_at > stamp
        ).values(used_at=stamp))
        session.commit()
        if claimed.rowcount != 1:
            raise _invalid()
        row = session.execute(select(model).where(model.code_hash == code_hash)).scalar_one()
        if not hmac.compare_digest(_sha256_hex(device_secret or "").encode(), row.device_hash.encode()):
            raise _invalid()
        if row.purpose != purpose:
            raise _invalid()
        try:
            data = json.loads(self._cipher.decrypt_state(row.payload_enc))
        except ValueError:
            raise _invalid() from None
        if not isinstance(data, dict):
            raise _invalid()
        return data

    def prune(self, session: Session, *, older_than_seconds: int = 3600, now: float | None = None) -> int:
        """Delete rows that expired more than ``older_than_seconds`` ago. Returns the count. Commits."""
        cutoff = _naive_utc(now) - timedelta(seconds=older_than_seconds)
        removed = session.execute(delete(self._model).where(self._model.expires_at < cutoff)).rowcount
        session.commit()
        return int(removed)
