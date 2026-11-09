"""Shared pieces of the refresh sessions: types, token hashing, clock conversion, row and JWT minting.

Not part of the public surface; import from ``bond_auth_py`` or ``bond_auth_py.sessions``.
"""

import base64
import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from bond_auth_py.errors import RefreshRevoked
from bond_auth_py.settings import AuthSettings
from bond_auth_py.tokens import create_access_token

MAX_TOKEN_CHARS = 256
MAX_ROTATION_ID_CHARS = 64
MAX_DEVICE_LABEL_CHARS = 80
DAY = 86400.0


@dataclass(frozen=True)
class SessionSpec:
    """What goes into the access JWT. ``sub`` is the user id (it becomes ``sub`` and ``user_id``)."""

    sub: str
    name: str | None = None
    capabilities: list[str] = field(default_factory=list)
    extra_claims: dict = field(default_factory=dict)


@dataclass(frozen=True)
class IssuedSession:
    access_jwt: str = field(repr=False)
    refresh_token: str = field(repr=False)  # plaintext, returned once; only its hash is stored
    family_id: str
    expires_in: int  # access token lifetime, seconds
    user_id: str


def to_naive(ts: float) -> datetime:
    """Epoch seconds to the naive-UTC datetime the columns hold."""
    return datetime.fromtimestamp(ts, UTC).replace(tzinfo=None)


def to_epoch(value: datetime) -> float:
    """Naive datetimes are UTC (that is how the columns are stored); aware ones are honoured."""
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).timestamp()


def token_hash(token: str) -> str:
    """``sha256`` of the token, base64url without padding (43 characters)."""
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def hash_or_refuse(token: object) -> str:
    """The hash of a plausible token; ``RefreshRevoked`` for an empty, non-string or oversized one (no lookup)."""
    if not isinstance(token, str) or not token.strip() or len(token) > MAX_TOKEN_CHARS:
        raise RefreshRevoked()
    return token_hash(token.strip())


def clean_rotation_id(value: object) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= MAX_ROTATION_ID_CHARS:
        return value
    return None


def mint_access(spec: SessionSpec, *, family_id: str, settings: AuthSettings, t: float) -> tuple[str, int]:
    """The access JWT (``iat`` = ``t``, ``sid`` = family id) and its lifetime in seconds."""
    minutes = settings.session_access_ttl_minutes
    jwt_ = create_access_token(sub=spec.sub, name=spec.name, capabilities=list(spec.capabilities),
                               settings=settings, extra_claims={**spec.extra_claims, "sid": family_id},
                               now=datetime.fromtimestamp(t, UTC), ttl=timedelta(minutes=minutes))
    return jwt_, minutes * 60


def add_row(session, model, *, user_id: str, family_id: str, provider: str, auth_time: datetime,
            family_expires_at: datetime | None, t: float, settings: AuthSettings, parent_id: str | None,
            rotation_id: str | None, device_label: str | None, last_probed_at: datetime | None) -> str:
    """Insert a refresh-token row and return the plaintext token. ``expires_at`` slides but never passes the cap
    (``family_expires_at`` is None when there is none)."""
    token = secrets.token_urlsafe(32)
    sliding = t + settings.refresh_ttl_days * DAY
    session.add(model(
        id=str(uuid.uuid4()), family_id=family_id, user_id=user_id, token_hash=token_hash(token),
        parent_id=parent_id, provider=provider, auth_time=auth_time, family_expires_at=family_expires_at,
        expires_at=to_naive(sliding) if family_expires_at is None else min(to_naive(sliding), family_expires_at),
        created_at=to_naive(t), rotation_id=rotation_id,
        device_label=(device_label or None) and device_label[:MAX_DEVICE_LABEL_CHARS],
        last_probed_at=last_probed_at))
    session.flush()
    return token


def revoke_family(session, model, *, family_id: str, reason: str, now: float | None = None) -> int:
    """Revoke every live row of the family. Returns the number of rows revoked. The caller commits."""
    stamp = to_naive(time.time() if now is None else now)
    result = session.execute(
        update(model).where(model.family_id == family_id, model.revoked_at.is_(None))
        .values(revoked_at=stamp, revoke_reason=reason[:16]).execution_options(synchronize_session="fetch"))
    return result.rowcount or 0
