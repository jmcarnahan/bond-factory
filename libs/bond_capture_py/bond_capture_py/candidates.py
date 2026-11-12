"""Candidates: what ``POST /tasks/parse`` returns (fixture ``../../fixtures/capture/expected_candidates.json``).

Nothing is created from a candidate: the client shows them for review and the user saves. ``to_dict`` is the wire
shape, key order included.
"""

from dataclasses import dataclass, field

LOW_CONFIDENCE = 0.5  # below this an item carries the flag ``low_confidence``
FLAG_LOW_CONFIDENCE = "low_confidence"
REASONS = ("model_unavailable", "invalid_output")


@dataclass(frozen=True)
class LinkCandidate:
    """A name the note mentioned and the contacts it might mean: ``candidates`` is ``[{id, label}]``."""

    text: str
    kind: str = "contact"
    candidates: tuple = ()

    def to_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind, "candidates": [dict(c) for c in self.candidates]}


@dataclass(frozen=True)
class TaskCandidate:
    title: str
    due_date: str  # YYYY-MM-DD
    due_time: str | None = None  # HH:MM local, only when the note states a clock time
    due_defaulted: bool = False  # the note had no date, so today was used
    priority: int | None = None  # 1 to 3
    links: tuple[LinkCandidate, ...] = ()
    confidence: float = 1.0
    flags: tuple[str, ...] = ()
    degraded: bool = False
    kind: str = field(default="task", init=False)

    def to_dict(self) -> dict:
        return {
            "kind": "task",
            "title": self.title,
            "due_date": self.due_date,
            "due_time": self.due_time,
            "due_defaulted": self.due_defaulted,
            "priority": self.priority,
            "links": [link.to_dict() for link in self.links],
            "confidence": self.confidence,
            "flags": list(self.flags),
            "degraded": self.degraded,
        }


@dataclass(frozen=True)
class EventCandidate:
    title: str
    start_date: str
    start_time: str | None = None
    all_day: bool = False
    end_date: str | None = None
    end_time: str | None = None
    links: tuple[LinkCandidate, ...] = ()
    confidence: float = 1.0
    flags: tuple[str, ...] = ()
    degraded: bool = False
    kind: str = field(default="event", init=False)

    def to_dict(self) -> dict:
        return {
            "kind": "event",
            "title": self.title,
            "start_date": self.start_date,
            "start_time": self.start_time,
            "all_day": self.all_day,
            "end_date": self.end_date,
            "end_time": self.end_time,
            "links": [link.to_dict() for link in self.links],
            "confidence": self.confidence,
            "flags": list(self.flags),
            "degraded": self.degraded,
        }


@dataclass(frozen=True)
class CaptureResult:
    """``items`` are task and event candidates; ``degraded`` is True when no model answered; ``reason`` is then
    ``model_unavailable`` or ``invalid_output``, else None."""

    items: tuple = ()
    degraded: bool = False
    reason: str | None = None

    def to_dict(self) -> dict:
        return {"items": [item.to_dict() for item in self.items], "degraded": self.degraded, "reason": self.reason}
