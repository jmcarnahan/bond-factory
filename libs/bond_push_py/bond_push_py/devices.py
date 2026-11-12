"""Device registry services. Every function takes a session, flushes, and never commits. ``now`` is naive UTC
(an aware value is converted).

Refusals raise ``PushError``; so does every non-string where a string is required.
"""

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from bond_push_py.errors import PushError
from bond_push_py.models import ENVIRONMENTS, PLATFORMS
from bond_push_py.timeutil import to_naive_utc


def device_row_id(user_id: str, device_id: str) -> str:
    """The id of a device row: ``"d_"`` plus the first 32 hex characters of ``sha256("<user_id>|<device_id>")``
    (UTF-8). The phone computes the same value, so REST and sync address one row."""
    return "d_" + hashlib.sha256(f"{user_id}|{device_id}".encode()).hexdigest()[:32]


def check_device_id(device_id: Any) -> None:
    if not isinstance(device_id, str) or not device_id.strip():
        raise PushError("device_id_required")
    if len(device_id) > 64:
        raise PushError("device_id_too_long")


def check_token(token: Any) -> None:
    if not isinstance(token, str) or not token.strip():
        raise PushError("token_required")
    if len(token) > 255:
        raise PushError("token_too_long")


def check_fields(*, token: Any, platform: Any, environment: Any, topic: Any) -> None:
    """The validation ``register_device`` applies to a write (and a sync patch applies to what it changes)."""
    check_token(token)
    if not isinstance(platform, str) or platform not in PLATFORMS:
        raise PushError("invalid_platform")
    if not isinstance(environment, str) or environment not in ENVIRONMENTS:
        raise PushError("invalid_environment")
    if topic is not None:
        if not isinstance(topic, str):
            raise PushError("invalid_topic")
        if len(topic) > 255:
            raise PushError("topic_too_long")


def release_token(session: Any, device_model: Any, token: str, keep: Any = None) -> None:
    """Delete the row (other than ``keep``) that holds ``token`` and flush, so the unique token is free."""
    holders = session.execute(select(device_model).where(device_model.token == token)).scalars().all()
    moved = False
    for row in holders:
        if row is not keep:
            session.delete(row)
            moved = True
    if moved:
        session.flush()


def register_device(session: Any, device_model: Any, *, user_id: str, device_id: str, token: str, platform: str,
                    environment: str, topic: str | None, now: datetime, row_id: str | None = None) -> Any:
    """Upsert by (user_id, device_id): new token and ``last_seen_at``, clears ``disabled_at``. A token already
    held by another row (another device or user: a phone changed hands) moves: the old row is deleted, then
    this one is written, in one flush, so the unique token never collides. Invalid input (platform,
    environment, empty or non-string token or device id) is a coded ``PushError``, never a database error.
    Returns the row. A NEW row's id is ``row_id`` if given, else ``device_row_id(user_id, device_id)``; an
    existing row keeps its id (a random one only for rows made before that formula existed).

    Two writers racing on one (user, device) or one token: the write runs in a savepoint, and the loser of a
    unique violation re-reads and updates (a token held by the winner moves). A second violation is a coded
    ``device_conflict``, never an ``IntegrityError``."""
    check_device_id(device_id)
    check_fields(token=token, platform=platform, environment=environment, topic=topic)
    now = to_naive_utc(now)
    for attempt in (1, 2):
        row = session.execute(
            select(device_model).where(device_model.user_id == user_id, device_model.device_id == device_id)
        ).scalar_one_or_none()
        release_token(session, device_model, token, keep=row)
        try:
            with session.begin_nested():
                if row is None:
                    row = device_model(id=row_id or device_row_id(user_id, device_id), user_id=user_id,
                                       device_id=device_id, created_at=now)
                    session.add(row)
                row.token = token
                row.platform = platform
                row.environment = environment
                row.topic = topic
                row.last_seen_at = now
                row.disabled_at = None
                session.flush()
            return row
        except IntegrityError:
            if attempt == 2:
                raise PushError("device_conflict") from None
    raise AssertionError("unreachable")  # pragma: no cover


def unregister_device(session: Any, device_model: Any, *, user_id: str, device_id: str) -> bool:
    """Delete the row; True if one existed. Deleting what is gone is success."""
    row = session.execute(
        select(device_model).where(device_model.user_id == user_id, device_model.device_id == device_id)
    ).scalar_one_or_none()
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def devices_for(session: Any, device_model: Any, user_id: str, platform: str | None = "ios") -> list:
    """The user's live rows (``disabled_at`` null) for ``platform`` (default "ios", the only platform this lib
    sends to; ``None`` means every platform), newest ``last_seen_at`` first."""
    stmt = select(device_model).where(device_model.user_id == user_id, device_model.disabled_at.is_(None))
    if platform is not None:
        stmt = stmt.where(device_model.platform == platform)
    stmt = stmt.order_by(device_model.last_seen_at.desc(), device_model.id)
    return list(session.execute(stmt).scalars().all())
