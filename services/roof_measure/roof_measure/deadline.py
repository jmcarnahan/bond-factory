"""A shared wall-clock budget for one job: every stage asks it for its timeout and checks it between steps."""

from __future__ import annotations

import time
from dataclasses import dataclass


class DeadlineExceeded(TimeoutError):
    """The job ran out of time; ``stage`` names where."""

    def __init__(self, stage: str):
        super().__init__(f"deadline exceeded during {stage}")
        self.stage = stage


@dataclass(frozen=True)
class Deadline:
    at: float  # time.monotonic() value at which the budget is spent

    @classmethod
    def after(cls, seconds: float) -> Deadline:
        return cls(time.monotonic() + max(0.0, float(seconds)))

    def remaining(self) -> float:
        return max(0.0, self.at - time.monotonic())

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def check(self, stage: str) -> None:
        if self.expired():
            raise DeadlineExceeded(stage)

    def timeout(self, cap: float) -> float:
        """A per-call timeout: ``cap`` or what is left, whichever is smaller, never below 1 ms."""
        return max(0.001, min(float(cap), self.remaining()))
