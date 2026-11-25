"""Caller answers that steer the plane engine (``library.measure(..., hints=)``).

A hint is a question the caller asked a person and the answer. No hint, or a hint that equals today's behaviour, changes
nothing: the same parameters, the same cache key, the same output.

    ``steps``: ``False`` = "there is no wall or step between the two parts of this roof". A step line between two
    PITCHED sections whose fitted planes agree at the seam is then typed from the planes (valley, ridge, hip).
    ``True`` is today's behaviour (the points decide)."""

from __future__ import annotations

from typing import Any

from . import params as _params
from .params import EngineParams

ALLOWED: dict[str, type] = {"steps": bool}


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
    out = {k: v for k, v in hints.items() if not (k == "steps" and v is True)}
    return out or None


def params_from_hints(hints: dict[str, Any] | None, base: EngineParams | None = None) -> EngineParams:
    """``base`` itself (the same object) when no hint changes anything, else a copy with the hints applied."""
    base = base if base is not None else _params.DEFAULT  # looked up at call time (tests swap the default)
    clean = clean_hints(hints)
    if clean is None:
        return base
    if clean.get("steps") is False:
        base = base.replace(pitched_steps=False)
    return base
