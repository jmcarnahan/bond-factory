"""Verdict vocabulary: what a handler raises or returns, result constructors, and the database-down classifier."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from .envelope import OpResult

INVALID = "invalid"
UNSUPPORTED = "unsupported"
CONFLICT = "conflict"
SERVER_ERROR = "server_error"
ALREADY = "already"
NOT_FOUND = "not_found"
FORBIDDEN = "forbidden"
RATE_LIMITED = "rate_limited"
CODES = (INVALID, UNSUPPORTED, CONFLICT, SERVER_ERROR, ALREADY, NOT_FOUND, FORBIDDEN, RATE_LIMITED)

NOT_SUPPORTED_MESSAGE = "Not supported"
USE_REST_MESSAGE = "Use the REST route"


class Rejected(Exception):
    """An op refused before or by a handler. ``code`` is the stable name the device stores."""

    code = INVALID

    def __init__(self, message: str = "", code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class Skipped(Exception):
    """Not an error: the op needed no work."""

    def __init__(self, code: str = ALREADY) -> None:
        super().__init__(code)
        self.code = code


class DbUnavailable(Exception):
    """The database, not the op, is the problem. The route must answer HTTP 503 so the client retries the whole batch.
    ``db_unavailable`` is a marker a host's error middleware can read (``getattr(exc, "db_unavailable", False)``) to answer 503."""

    db_unavailable = True


@dataclass(frozen=True)
class Resolved:
    """Returned by a handler when the server row that satisfied a put has a different id than the device chose."""

    id: str


def ok(seq: int, resolved_id: str | None = None) -> OpResult:
    return OpResult(seq=seq, status="ok", resolved_id=resolved_id)


def rejected(seq: int, code: str, message: str | None = None) -> OpResult:
    return OpResult(seq=seq, status="rejected", code=code, message=message if message is not None else code)


def skipped(seq: int, code: str = ALREADY) -> OpResult:
    return OpResult(seq=seq, status="skipped", code=code)


# SQLSTATE classes that mean the database, not the op: 08 connection, 40 rollback, 53 resources, 57 operator intervention.
_DOWN_CLASSES = ("08", "40", "53", "57")
# 57014 is a statement timeout on THIS op: a per-op verdict, so one slow op cannot wedge a device's queue.
_NOT_DOWN = frozenset({"57014"})
_SQLITE_DOWN = ("database is locked", "unable to open database file")


def is_database_down(exc: BaseException) -> bool:
    """True when the whole request must fail and be retried: interface errors, pool timeouts, an invalidated connection,
    or an OperationalError with a SQLSTATE in class 08/40/53/57 (not 57014), or with no SQLSTATE from a non-SQLite driver.
    On SQLite only "database is locked" and "unable to open database file" count."""
    if isinstance(exc, (InterfaceError, PoolTimeout)):
        return True
    if not isinstance(exc, OperationalError):
        return False
    if getattr(exc, "connection_invalidated", False):
        return True
    orig = getattr(exc, "orig", None)
    code = str(getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None) or "")
    if code:
        return code[:2] in _DOWN_CLASSES and code not in _NOT_DOWN
    if isinstance(orig, sqlite3.Error):
        # SQLite has no SQLSTATE and reports bugs ("no such column") as OperationalError too: only a locked or unopenable
        # file is "down". Same rule as bond_service_kit.errors.is_db_unavailable, copied because libs never import libs.
        return any(m in str(orig).lower() for m in _SQLITE_DOWN)
    return True  # another driver with no SQLSTATE: a refused or dropped connection
