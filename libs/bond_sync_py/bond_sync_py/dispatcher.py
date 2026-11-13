"""Applies a device's queued local writes by calling host handlers, one transaction per op.

A refused op never undoes or stops its neighbours; every outcome is an ``OpResult``. Only an unavailable database escapes
(as ``DbUnavailable``), so the route answers 503 and the client retries the whole request. Everything else, an unmapped bug
included, becomes a per-op verdict: a client retries any 4xx/5xx forever, so a validation failure is never an HTTP error.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.exc import DataError, IntegrityError

from .coerce import coerce, has_nul
from .envelope import OpResult, UploadOp, UploadRequest, UploadResponse, server_now_iso
from .replay import LoggedBugs
from .routes import Ctx, Host, Route, route_for
from .verdicts import (
    CONFLICT,
    INVALID,
    SERVER_ERROR,
    UNSUPPORTED,
    USE_REST_MESSAGE,
    DbUnavailable,
    Rejected,
    Resolved,
    Skipped,
    is_database_down,
    ok,
    rejected,
    skipped,
)

LOGGER = logging.getLogger(__name__)
LOGGED_BUGS = LoggedBugs()
_LOGGED_HANDLER_BUGS: set[tuple[str, str | None, str]] = set()

# Stricter than the wire's 256 chars on purpose: ids are device-minted UUIDs or server ids, never user text.
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

__all__ = ["Ctx", "Host", "Route", "apply", "reject_for", "route_for", "upload"]


def reject_for(host: Host, session, user, op: UploadOp, exc: Exception) -> OpResult | None:
    """What an exception from one op means for the device, or None when the database is unavailable (the session is
    already rolled back)."""
    text = str(exc) or None
    if isinstance(exc, Skipped):
        return skipped(op.seq, exc.code)
    if isinstance(exc, Rejected):
        return rejected(op.seq, exc.code, text)
    if host.reject_for is not None:
        mapped = host.reject_for(session, user, op, exc)
        if mapped is not None:
            return mapped
    if isinstance(exc, IntegrityError):
        if op.op == "put" and host.already_written is not None and host.already_written(session, user, op):
            return ok(op.seq)  # the same put arriving twice: the winner's row is the answer
        return rejected(op.seq, CONFLICT)
    if isinstance(exc, (DataError, ValueError, KeyError, TypeError, RecursionError, OverflowError)):
        return rejected(op.seq, INVALID)
    if is_database_down(exc):
        return None
    if LOGGED_BUGS.first_time(op.table, op.id):
        LOGGER.error("sync upload: unexpected %s on %s %s %s", type(exc).__name__, op.table, op.action, op.id, exc_info=exc)
    else:
        LOGGER.warning("sync upload: unexpected %s again on %s %s %s", type(exc).__name__, op.table, op.action, op.id)
    return rejected(op.seq, SERVER_ERROR)


def apply(session_factory, host: Host, ctx: Ctx, op: UploadOp, *, close_sessions: bool = True) -> OpResult:
    """Run one op in its own transaction and say what happened. Raises ``DbUnavailable`` when the database is down.
    ``close_sessions=False`` leaves the session open (the op is still committed or rolled back), for a factory that hands
    out a request-scoped session its owner closes."""
    session = session_factory()
    try:
        try:
            if _ID.fullmatch(op.id) is None:  # ASCII, the whole string: no Unicode digits, no trailing newline
                raise Rejected("That id is not valid", code=INVALID)
            if op.table in host.rest_only:
                raise Rejected(USE_REST_MESSAGE, code=UNSUPPORTED)
            route = route_for(host, op)
            data = coerce(
                host.tables, op.table, op.data, route.reads,
                client_bools=host.client_bools.get(op.table, frozenset()),
                client_json=host.client_json.get(op.table, frozenset()),
                optional=route.optional,
            )
            if has_nul(op.id) or has_nul(data):
                raise Rejected("That value is not valid", code=INVALID)
            try:
                outcome = route.handler(session, ctx, op, data)
            except (KeyError, TypeError, RecursionError) as exc:
                _log_handler_bug(op, exc)  # still an `invalid` verdict, but a server bug must not look like bad client data
                raise
            session.commit()
            return ok(op.seq, outcome.id if isinstance(outcome, Resolved) else None)
        except Exception as exc:
            result = _verdict_for(host, session, ctx, op, exc)
            if result is None:
                raise DbUnavailable(str(exc)) from exc
            return result
    finally:
        if close_sessions:
            try:
                session.close()
            except Exception:
                LOGGER.warning("sync upload: closing the session failed on %s %s", op.table, op.id, exc_info=True)


def _log_handler_bug(op: UploadOp, exc: Exception) -> None:
    """One ERROR with traceback per (table, action, error type); the client retries, so more would only be noise."""
    key = (op.table, op.action, type(exc).__name__)
    if key not in _LOGGED_HANDLER_BUGS:
        _LOGGED_HANDLER_BUGS.add(key)
        LOGGER.error("sync upload: handler raised %s on %s %s", key[2], op.table, op.action, exc_info=exc)


def _verdict_for(host: Host, session, ctx: Ctx, op: UploadOp, exc: Exception) -> OpResult | None:
    """Roll back and map ``exc``. A failure in the rollback or in a host hook becomes ``server_error``, or None (database
    down) when that failure is a connection problem: it never escapes as a raw 500."""
    try:
        session.rollback()
        return reject_for(host, session, ctx.user, op, exc)
    except Exception as inner:
        if is_database_down(inner):
            return None
        LOGGER.error("sync upload: %s while handling %s on %s %s", type(inner).__name__, type(exc).__name__, op.table, op.id,
                     exc_info=inner)
        return rejected(op.seq, SERVER_ERROR)


def upload(
    session_factory, host: Host, ctx: Ctx, body: UploadRequest, *,
    close_sessions: bool = True, now: Callable[[], datetime] | None = None,
) -> UploadResponse:
    """Apply the ops in ``seq`` order. One result per op; a refused op never stops the next.
    ``now`` is the clock behind ``server_now`` (default: the real time); ``close_sessions`` is passed to ``apply``."""
    ops = sorted(body.ops, key=lambda o: o.seq)
    results = [apply(session_factory, host, ctx, op, close_sessions=close_sessions) for op in ops]
    return UploadResponse(results=results, server_now=server_now_iso(now() if now is not None else None))
