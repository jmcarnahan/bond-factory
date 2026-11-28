"""Caller answers that steer the plane engine (``library.measure(..., hints=)``).

There are none today. The one that existed, ``steps`` ("there is no wall or step between the two parts of this roof"), is
retired: the step test now measures the jump robustly (``edge_measure.points_jump``) and a step line between two PITCHED
facets whose fitted planes agree at the seam is always typed from the planes (``edges._planes_agree_pitched``), so the
answer changed nothing on the 160 tuning houses or the three accuracy houses. A hint to add later is a key of ``ALLOWED``
and a parameter the hint switches (left out of ``EngineParams.stable_hash`` while at its default so no cached result moves)."""

from __future__ import annotations

from typing import Any

from . import params as _params
from .params import EngineParams

ALLOWED: dict[str, type] = {}


def clean_hints(hints: dict[str, Any] | None) -> dict[str, Any] | None:
    """The validated hints that change anything, or None. Unknown key or wrong type: ValueError naming the key."""
    if hints is None:
        return None
    if not isinstance(hints, dict):
        raise ValueError("hints must be a dict or None")  # noqa: TRY004 - the contract says ValueError
    for k, v in hints.items():
        if k not in ALLOWED:
            raise ValueError(f"unknown hint {k!r}; accepted: {sorted(ALLOWED)}")
        if not isinstance(v, ALLOWED[k]):
            raise ValueError(f"hint {k!r} must be {ALLOWED[k].__name__}, got {type(v).__name__}")  # noqa: TRY004
    return None


def params_from_hints(hints: dict[str, Any] | None, base: EngineParams | None = None) -> EngineParams:
    """``base`` itself (the same object): no hint changes a parameter today. Bad hints raise as ``clean_hints`` does."""
    clean_hints(hints)
    return base if base is not None else _params.DEFAULT  # looked up at call time (tests swap the default)
