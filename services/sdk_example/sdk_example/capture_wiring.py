"""REPLACE the fake model with a vendor client; keep the guard as a pattern. Fake mode only gets the fake model.

    ReplayLlm      an `LlmClient` that answers `fixtures/capture/model_output.json` whatever the note says, or
                   raises `LlmUnavailable` while `down` is set (the switch the walk uses to see the degraded path)
    RateGuard      a per-user `CaptureGuard`: at most `limit` parses per `window` seconds (429 `capture_denied`)
    EventLog       what the demo's "accept event" stub recorded (in memory; a real app creates a calendar event)
"""

from __future__ import annotations

import itertools
import json
import time
from collections import defaultdict, deque
from pathlib import Path

from bond_capture_py import CaptureDenied, LlmUnavailable

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "capture" / "model_output.json"


class ReplayLlm:
    def __init__(self, path: Path = FIXTURE) -> None:
        self.path = path
        self.down = False
        self.calls = 0

    def complete_json(self, system: str, user: str, schema: dict, timeout_s: float) -> dict:
        self.calls += 1
        if self.down:
            raise LlmUnavailable()
        return json.loads(self.path.read_text())


class RateGuard:
    """Sliding window per user. The clock is injectable so a test needs no sleep."""

    def __init__(self, limit: int = 20, window: float = 60.0, clock=time.monotonic) -> None:
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, user_id: str, text: str) -> None:
        now = self.clock()
        hits = self.hits[user_id]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise CaptureDenied()
        hits.append(now)


class EventLog:
    """Accepted event candidates, newest last, bounded."""

    def __init__(self, keep: int = 200) -> None:
        self.items: deque[dict] = deque(maxlen=keep)
        self.counter = itertools.count(1)

    def add(self, user_id: str, event: dict) -> dict:
        row = {"id": f"ev-{next(self.counter)}", "user_id": user_id, **event}
        self.items.append(row)
        return row
