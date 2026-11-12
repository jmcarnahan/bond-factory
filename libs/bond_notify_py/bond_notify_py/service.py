"""Inbox services. Every function takes a session, flushes, and never commits. ``now`` is naive UTC.

Refusals raise ``NoticeError``.
"""

import re
from collections.abc import Collection
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update

from bond_notify_py.errors import NoticeError
from bond_notify_py.serialize import due_key
from bond_notify_py.timeutil import to_naive_utc

MAX_LIMIT = 200


def _cursor_time(value: datetime) -> str:
    """ISO Z; fractional seconds appear only when present, so paging stays exact on high-resolution stamps."""
    return value.isoformat(timespec="microseconds" if value.microsecond else "seconds") + "Z"


def notice_cursor(row: Any) -> str:
    """The opaque paging cursor of a row: ``"<created_at ISO Z>|<id>"``."""
    return f"{_cursor_time(row.created_at)}|{row.id}"


_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _parse_cursor(cursor: str) -> tuple[datetime, str]:
    """Strict: ``"<ISO datetime>|<id>"``; an offset is converted to naive UTC, anything else is invalid."""
    stamp, sep, row_id = str(cursor).partition("|")
    try:
        if not sep or not _ID.fullmatch(row_id):
            raise ValueError(cursor)
        return to_naive_utc(datetime.fromisoformat(stamp)), row_id
    except ValueError:
        raise NoticeError("invalid_cursor") from None


def list_notices(session: Any, notice_model: Any, user_id: str, *, unread: bool = False, limit: int = 50,
                 before: str | None = None) -> tuple[list, int, str | None]:
    """``(rows, unread_count, next_cursor)``: the user's undismissed notices ordered by ``(created_at desc, id
    desc)``, so rows written in one sweep with the same ``created_at`` never tie. ``before`` is a cursor from
    ``notice_cursor`` (the last row of the previous page); only rows strictly after it in that order are
    returned. ``next_cursor`` is the cursor of the last returned row when more rows remain, else None.
    ``unread_count`` counts all the user's unread, undismissed notices whatever the page."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    live = and_(notice_model.user_id == user_id, notice_model.dismissed_at.is_(None))
    query = select(notice_model).where(live)
    if unread:
        query = query.where(notice_model.read_at.is_(None))
    if before:
        stamp, row_id = _parse_cursor(before)
        query = query.where(or_(notice_model.created_at < stamp,
                                and_(notice_model.created_at == stamp, notice_model.id < row_id)))
    query = query.order_by(notice_model.created_at.desc(), notice_model.id.desc()).limit(limit + 1)
    rows = list(session.execute(query).scalars())
    more = len(rows) > limit
    rows = rows[:limit]
    count = session.execute(
        select(func.count()).select_from(notice_model).where(live, notice_model.read_at.is_(None))
    ).scalar_one()
    return rows, int(count), notice_cursor(rows[-1]) if more else None


def _owned(session: Any, notice_model: Any, user_id: str, notice_id: str) -> Any:
    row = session.get(notice_model, notice_id)
    if row is None:
        raise NoticeError("notice_not_found")
    if row.user_id != user_id:
        raise NoticeError("not_notice_owner")
    return row


def mark_read(session: Any, notice_model: Any, user_id: str, notice_id: str, now: datetime) -> Any:
    """Set ``read_at`` (idempotent). 404 ``notice_not_found``; 403 ``not_notice_owner``. Returns the row."""
    now = to_naive_utc(now)
    row = _owned(session, notice_model, user_id, notice_id)
    if row.read_at is None:
        row.read_at = now
    session.flush()
    return row


def mark_all_read(session: Any, notice_model: Any, user_id: str, now: datetime) -> int:
    """Read every unread notice of the user; returns how many changed."""
    now = to_naive_utc(now)
    result = session.execute(
        update(notice_model)
        .where(notice_model.user_id == user_id, notice_model.read_at.is_(None))
        .values(read_at=now)
        .execution_options(synchronize_session="fetch")
    )
    session.flush()
    return result.rowcount


def dismiss(session: Any, notice_model: Any, user_id: str, notice_id: str, now: datetime) -> Any:
    """Set ``dismissed_at`` (and ``read_at`` if unset). Same refusals as ``mark_read``. Returns the row."""
    now = to_naive_utc(now)
    row = _owned(session, notice_model, user_id, notice_id)
    if row.dismissed_at is None:
        row.dismissed_at = now
    if row.read_at is None:
        row.read_at = now
    session.flush()
    return row


def dismiss_for_source(session: Any, notice_model: Any, source_id: str, now: datetime, *,
                       user_ids: Collection[str] | None = None) -> int:
    """Put away every live notice of one task; the app calls it on complete and cancel. ``user_ids`` limits it
    to those users' notices (for example the old assignee after a reassignment); None means everyone and an
    empty collection dismisses nothing."""
    if user_ids is not None and not user_ids:
        return 0
    now = to_naive_utc(now)
    query = update(notice_model).where(notice_model.source_id == source_id, notice_model.dismissed_at.is_(None))
    if user_ids is not None:
        query = query.where(notice_model.user_id.in_(list(user_ids)))
    result = session.execute(
        query
        .values(dismissed_at=now, read_at=func.coalesce(notice_model.read_at, now))
        .execution_options(synchronize_session="fetch")
    )
    session.flush()
    return result.rowcount


def dismiss_stale(session: Any, notice_model: Any, source_id: str, due_at: Any, now: datetime) -> int:
    """Put away every user's live notices of one task whose ``data.due_at`` differs from ``due_at`` (an ISO Z
    string or a datetime); None puts away all of them. The app calls it when a task's due instant changes: a
    notice made for the old time must not linger. Compared in Python, so it is the same on every dialect."""
    now = to_naive_utc(now)
    keep = due_key(due_at)
    rows = session.execute(
        select(notice_model).where(notice_model.source_id == source_id, notice_model.dismissed_at.is_(None))
    ).scalars()
    changed = 0
    for row in rows:
        if keep is not None and due_key((row.data or {}).get("due_at")) == keep:
            continue
        row.dismissed_at = now
        if row.read_at is None:
            row.read_at = now
        changed += 1
    session.flush()
    return changed


def prune_notices(session: Any, notice_model: Any, now: datetime, *, read_days: int = 30,
                  max_days: int = 90) -> int:
    """Delete notices read or dismissed more than ``read_days`` ago, or created more than ``max_days`` ago."""
    now = to_naive_utc(now)
    read_cutoff = now - timedelta(days=read_days)
    result = session.execute(
        delete(notice_model)
        .where(or_(notice_model.read_at < read_cutoff, notice_model.dismissed_at < read_cutoff,
                   notice_model.created_at < now - timedelta(days=max_days)))
        .execution_options(synchronize_session="fetch")
    )
    session.flush()
    return result.rowcount
