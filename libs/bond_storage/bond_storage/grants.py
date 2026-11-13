"""Download grants: the capability behind a link such as ``/d/<token>``.

The recipient is not a user, so the URL IS the credential. Two rules:

1. The token is opaque and random (``token_urlsafe(32)``, 256 bits). Only its sha256 is stored, so the raw value exists once,
   in the return of ``mint``. Revoking is a column.
2. Every failure looks the same. Unknown, revoked, expired, used up and "the document is gone" all raise
   ``GrantUnavailable``; telling them apart would make the route an oracle for which tokens are real.

The lib ships no migration. The app attaches ``GrantsMixin`` to its own ``Base`` (``__tablename__`` defaults to
``download_grants``) and may constrain ``document_id`` to its documents table::

    class DownloadGrant(GrantsMixin, Base):
        __table_args__ = (sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),)

Functions take the session and the mapped ``grant_model``. Times are naive UTC (``sa.DateTime``); ``now`` is a callable so
tests can pin it. ``claim`` commits, so a second request sees the count at once.
"""

import hashlib
import secrets
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, Session, mapped_column

TOKEN_BYTES = 32
#: A request carrying more than this is refused before hashing, so a route cannot be made to hash megabytes.
MAX_TOKEN_LEN = 128
DEFAULT_TTL_DAYS = 30
DEFAULT_MAX_DOWNLOADS = 20
SHARE, VIEW = "share", "view"
MAX_IP_LEN = 200

Now = Callable[[], datetime]


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class GrantUnavailable(Exception):
    """This link cannot be served, for any reason. Deliberately one exception."""


class DocumentLike(Protocol):
    id: str
    storage_key: str
    filename: str
    content_type: str | None
    kind: str


class GrantsMixin:
    """Columns of ``download_grants``."""

    __tablename__ = "download_grants"

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True)
    document_id: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(sa.String(32), nullable=False, default=SHARE)
    owner_type: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    max_downloads: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    last_downloaded_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    last_ip: Mapped[str | None] = mapped_column(sa.String(MAX_IP_LEN), nullable=True)
    created_by: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, default=utcnow_naive,
                                                 onupdate=utcnow_naive)


def hash_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


#: The columns this lib owns. ``mint(extra=...)`` may not set any of them.
LIB_COLUMNS = frozenset(GrantsMixin.__annotations__)


def _live(model: Any, now: datetime, enforce_cap: bool = True) -> list[Any]:
    """Filters that match a grant that can still be used."""
    filters = [model.revoked_at.is_(None), model.expires_at > now]
    if enforce_cap:
        filters.append(sa.or_(model.max_downloads.is_(None),
                              sa.func.coalesce(model.download_count, 0) < model.max_downloads))  # NULL counts as 0
    return filters


def mint(session: Session, document: DocumentLike, *, grant_model: Any, user_id: str | None, purpose: str = SHARE,
         owner_type: str | None = None, owner_id: str | None = None, ttl_days: int = DEFAULT_TTL_DAYS,
         max_downloads: int | None = DEFAULT_MAX_DOWNLOADS, ttl_seconds: int | None = None,
         extra: Mapping[str, Any] | None = None, now: Now = utcnow_naive) -> tuple[Any, str]:
    """Create a grant for ``document``; returns ``(row, raw_token)``. The raw token is never stored.

    ``owner_type`` / ``owner_id`` default to the document's own, when it has them. ``ttl_seconds`` wins over ``ttl_days``.
    ``extra`` sets the app's own columns on the row; a key that names one of this lib's columns raises ``ValueError``.
    """
    clash = sorted(LIB_COLUMNS & set(extra or ()))
    if clash:
        raise ValueError(f"extra cannot set the grant's own columns: {clash}")
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    stamp = now()
    ttl = timedelta(seconds=max(1, int(ttl_seconds))) if ttl_seconds else timedelta(days=max(1, int(ttl_days)))
    grant = grant_model(
        token_hash=hash_token(raw), document_id=document.id, purpose=purpose,
        owner_type=owner_type or getattr(document, "owner_type", None),
        owner_id=owner_id or getattr(document, "owner_id", None),
        expires_at=stamp + ttl, max_downloads=max_downloads, download_count=0, created_by=user_id,
        created_at=stamp, updated_at=stamp, **(extra or {}))
    session.add(grant)
    session.flush()
    return grant, raw


def resolve(session: Session, raw_token: str, *, grant_model: Any,
            document_loader: Callable[[Session, str], DocumentLike | None],
            enforce_cap: bool = True, now: Now = utcnow_naive) -> tuple[Any, DocumentLike]:
    """The grant and its document, or ``GrantUnavailable``. Cheapest checks first.

    ``enforce_cap=False`` ignores ``max_downloads`` (for an app that counts downloads but never limits them). Pass the
    same value to ``claim``, which applies the same guard."""
    token = (raw_token or "").strip()
    if not token or len(token) > MAX_TOKEN_LEN:
        raise GrantUnavailable
    grant = session.execute(sa.select(grant_model).where(grant_model.token_hash == hash_token(token))).scalar_one_or_none()
    if grant is None or grant.revoked_at is not None:
        raise GrantUnavailable
    if grant.expires_at is None or grant.expires_at <= now():
        raise GrantUnavailable
    if enforce_cap and grant.max_downloads is not None and (grant.download_count or 0) >= grant.max_downloads:
        raise GrantUnavailable
    document = document_loader(session, grant.document_id)
    if document is None:
        raise GrantUnavailable
    return grant, document


def claim(session: Session, grant: Any, ip: str | None = None, *, enforce_cap: bool = True, commit: bool = True,
          now: Now = utcnow_naive) -> bool:
    """Use one download, atomically: ONE guarded UPDATE that only matches while the link is live, so two simultaneous
    downloads of a single-use link cannot both win. True when this call got it. Commits, unless ``commit=False``
    (the caller then commits or rolls back, so its own writes and the claim land together)."""
    model = type(grant)
    stamp = now()
    values: dict[str, Any] = {"download_count": sa.func.coalesce(model.download_count, 0) + 1,  # NULL counts as 0
                              "last_downloaded_at": stamp, "updated_at": stamp}
    if ip:
        values["last_ip"] = ip[:MAX_IP_LEN]
    result = session.execute(sa.update(model).where(model.id == grant.id, *_live(model, stamp, enforce_cap))
                             .values(**values).execution_options(synchronize_session=False))
    if commit:
        session.commit()
    session.refresh(grant)
    return result.rowcount == 1


def record_download(grant: Any, ip: str | None = None, *, now: Now = utcnow_naive) -> None:
    """Count a download on the loaded row (for callers that do not use ``claim``)."""
    stamp = now()
    grant.download_count = (grant.download_count or 0) + 1
    grant.last_downloaded_at = grant.updated_at = stamp
    if ip:
        grant.last_ip = ip[:MAX_IP_LEN]


def has_live_link(session: Session, owner_type: str, owner_id: str, *, grant_model: Any, now: Now = utcnow_naive) -> bool:
    """Is there a link for this owner that still works? Needs no raw token."""
    query = sa.select(grant_model.id).where(grant_model.owner_type == owner_type, grant_model.owner_id == owner_id,
                                            *_live(grant_model, now())).limit(1)
    return session.execute(query).first() is not None


def revoke_for_owner(session: Session, owner_type: str, owner_id: str, *, grant_model: Any,
                     purpose: str | None = None, now: Now = utcnow_naive) -> int:
    """Revoke every unrevoked grant for the owner (optionally one purpose); returns how many."""
    query = sa.select(grant_model).where(grant_model.owner_type == owner_type, grant_model.owner_id == owner_id,
                                         grant_model.revoked_at.is_(None))
    if purpose:
        query = query.where(grant_model.purpose == purpose)
    stamp = now()
    rows = list(session.execute(query).scalars())
    for grant in rows:
        grant.revoked_at = stamp
    return len(rows)


def revoke(grant: Any, *, now: Now = utcnow_naive) -> None:
    grant.revoked_at = now()
