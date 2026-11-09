"""What the host application gives the dispatcher: routes, context and hooks. No framework, no table knowledge."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .envelope import OpResult, UploadOp
from .verdicts import NOT_SUPPORTED_MESSAGE, UNSUPPORTED, Rejected


@dataclass(frozen=True)
class Route:
    """``handler(session, ctx, op, data)`` returns None (ok) or ``Resolved``; it raises ``Rejected``, ``Skipped`` or a
    host error that ``Host.reject_for`` maps. ``reads`` lists the data keys the handler uses: the only ones coerced."""

    ops: frozenset
    handler: Callable
    reads: tuple = ()


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


def route_for(host: Host, op: UploadOp) -> Route:
    """The route for ``(table, action)``, falling back to ``(table, None)`` for single-action tables."""
    route = host.routes.get((op.table, op.action))
    if route is None and op.table in host.single_action:
        route = host.routes.get((op.table, None))
    if route is None or op.op not in route.ops:
        raise Rejected(NOT_SUPPORTED_MESSAGE, code=UNSUPPORTED)
    return route
