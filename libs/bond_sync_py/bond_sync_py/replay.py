"""Replay helpers: the client retries an upload until acknowledged, so every put must be safe to see twice."""

from __future__ import annotations

import threading
from collections import OrderedDict


class LoggedBugs:
    """Bounded memory of the ``(table, op id)`` pairs whose bug was already logged with a traceback: one traceback per op."""

    def __init__(self, maximum: int = 1000) -> None:
        self._seen: OrderedDict = OrderedDict()
        self._max = maximum
        self._lock = threading.Lock()  # ops run on several threadpool threads

    def first_time(self, table: str, op_id: str) -> bool:
        """Record the pair; True when it had not been seen."""
        key = (table, op_id)
        with self._lock:
            seen = key in self._seen
            self._seen[key] = None
            self._seen.move_to_end(key)
            while len(self._seen) > self._max:
                self._seen.popitem(last=False)
        return not seen


def written_by(session, model, owner_attr: str, user_id: str, op_id: str) -> bool:
    """True when the row the op's id names exists and belongs to the caller: a replay that lost a race, not a clash."""
    row = session.get(model, op_id)
    return row is not None and getattr(row, owner_attr) == user_id
