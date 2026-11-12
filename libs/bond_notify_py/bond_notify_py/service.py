"""Inbox services. Every function takes a session, flushes, and never commits. ``now`` is naive UTC.

Refusals raise ``NoticeError``.
"""

from datetime import datetime
from typing import Any

from bond_notify_py.timeutil import iso_z


def notice_cursor(row: Any) -> str:
    """The opaque paging cursor of a row: ``"<created_at ISO Z>|<id>"``."""
    return f"{iso_z(row.created_at)}|{row.id}"


def list_notices(session: Any, notice_model: Any, user_id: str, *, unread: bool = False, limit: int = 50,
                 before: str | None = None) -> tuple[list, int, str | None]:
    """``(rows, unread_count, next_cursor)``: the user's undismissed notices ordered by ``(created_at desc, id
    desc)``, so rows written in one sweep with the same ``created_at`` never tie. ``before`` is a cursor from
    ``notice_cursor`` (the last row of the previous page); only rows strictly after it in that order are
    returned. ``next_cursor`` is the cursor of the last returned row when more rows remain, else None.
    ``unread_count`` counts all the user's unread, undismissed notices whatever the page."""
    raise NotImplementedError("service.list_notices is not implemented yet")


def mark_read(session: Any, notice_model: Any, user_id: str, notice_id: str, now: datetime) -> Any:
    """Set ``read_at`` (idempotent). 404 ``notice_not_found``; 403 ``not_notice_owner``. Returns the row."""
    raise NotImplementedError("service.mark_read is not implemented yet")


def mark_all_read(session: Any, notice_model: Any, user_id: str, now: datetime) -> int:
    """Read every unread notice of the user; returns how many changed."""
    raise NotImplementedError("service.mark_all_read is not implemented yet")


def dismiss(session: Any, notice_model: Any, user_id: str, notice_id: str, now: datetime) -> Any:
    """Set ``dismissed_at`` (and ``read_at`` if unset). Same refusals as ``mark_read``. Returns the row."""
    raise NotImplementedError("service.dismiss is not implemented yet")


def dismiss_for_source(session: Any, notice_model: Any, source_id: str, now: datetime) -> int:
    """Put away every live notice of one task (all recipients); the app calls it on complete and cancel."""
    raise NotImplementedError("service.dismiss_for_source is not implemented yet")


def prune_notices(session: Any, notice_model: Any, now: datetime, *, read_days: int = 30,
                  max_days: int = 90) -> int:
    """Delete notices read or dismissed more than ``read_days`` ago, or created more than ``max_days`` ago."""
    raise NotImplementedError("service.prune_notices is not implemented yet")
