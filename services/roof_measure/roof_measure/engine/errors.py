"""Typed errors and the cooperative deadline of the roof engine."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .params import EngineParams


class EngineError(Exception):
    """Base of everything the engine raises on purpose."""


class EngineTimeout(EngineError):
    """The deadline (a ``time.monotonic()`` value) passed while the engine was working."""


class EngineInputError(EngineError):
    """The input cannot be measured (unusable footprint, no finite points)."""


class EngineFailure(EngineError):
    """An unexpected internal failure, wrapped so callers only ever see EngineError subclasses."""


@dataclass(frozen=True)
class Ctx:
    """Parameters and deadline travelling together through the long loops."""

    p: EngineParams
    deadline: float | None = None

    def check(self) -> None:
        """Raise EngineTimeout once the deadline has passed (no-op without a deadline)."""
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise EngineTimeout("roof engine deadline exceeded")
