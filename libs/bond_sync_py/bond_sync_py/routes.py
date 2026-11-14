"""What the host application gives the dispatcher: routes, context and hooks. No framework, no table knowledge."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .envelope import OpResult, UploadOp
from .verdicts import NOT_SUPPORTED_MESSAGE, UNSUPPORTED, Rejected


@dataclass(frozen=True)
class Route:
    """``handler(session, ctx, op, data)`` returns None (ok) or ``Resolved``; it raises ``Rejected``, ``Skipped`` or a
    host error that ``Host.reject_for`` maps. ``reads`` lists the data keys the handler uses: the only ones coerced.
    An empty ``reads`` (the default) is NOT "coerce nothing": it means "no list given", so every key in the op's data is
    coerced. List the keys to restrict coercion, so a malformed column the handler ignores cannot reject the op."""

    ops: frozenset
    handler: Callable
    reads: tuple = ()
    #: names in ``reads`` that are left out of the data when their value is blank or unreadable, instead of rejecting the op
    optional: tuple = ()


@dataclass
class Ctx:
    """``user`` is the session user (never from the payload). ``background`` has ``add_task(fn, *args)`` or is None."""

    user: Any
    background: Any = None


@dataclass(frozen=True)
class Host:
    """Everything the dispatcher needs from the application."""

    routes: Mapping[tuple, Route]
    tables: Mapping[str, Any] = field(default_factory=dict)  # name -> sqlalchemy Table, for coercion
    single_action: frozenset = frozenset()  # tables where a stray ``action`` is ignored
    rest_only: frozenset = frozenset()  # tables that never travel through the upload route
    #: ``(session, user, op, exc) -> OpResult | None``: map the host's own errors; None falls through
    reject_for: Callable[[Any, Any, UploadOp, Exception], OpResult | None] | None = None
    #: ``(session, user, op) -> bool``: the row an IntegrityError hit is the caller's own (a replay that lost a race)
    already_written: Callable[[Any, Any, UploadOp], bool] | None = None
    client_bools: Mapping[str, frozenset] = field(default_factory=dict)
    client_json: Mapping[str, frozenset] = field(default_factory=dict)
    #: Overrides the op-id rule (default ``[A-Za-z0-9_-]{1,64}``), applied with ``fullmatch``. For a host whose devices
    #: already hold longer or punctuated ids. Use explicit ASCII classes; the wire still caps an id at 256 chars.
    #: ``\w``/``\d`` admit Unicode and a trailing ``$`` admits a final newline, so prefer ``[A-Za-z0-9...]`` classes.
    id_pattern: re.Pattern[str] | None = None

    def __post_init__(self) -> None:
        pattern = self.id_pattern
        if pattern is not None and not (isinstance(pattern, re.Pattern) and isinstance(pattern.pattern, str)):
            raise TypeError("Host.id_pattern must be a compiled str pattern (re.compile(...)) or None")


def route_for(host: Host, op: UploadOp) -> Route:
    """The route for ``(table, action)``, falling back to ``(table, None)`` for single-action tables."""
    route = host.routes.get((op.table, op.action))
    if route is None and op.table in host.single_action:
        route = host.routes.get((op.table, None))
    if route is None or op.op not in route.ops:
        raise Rejected(NOT_SUPPORTED_MESSAGE, code=UNSUPPORTED)
    return route
