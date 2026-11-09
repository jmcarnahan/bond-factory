"""Structural seams the app wires. This lib imports no sibling lib: the real objects come from the app."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class Scheduler(Protocol):
    """Shape of the job queue's enqueue plus a cancel. ``dedupe_key`` names one live job per task reminder."""

    def enqueue(self, session: Any, *, job_type: str, payload: dict, run_at: datetime, dedupe_key: str) -> None: ...

    def cancel(self, session: Any, *, dedupe_key: str) -> None: ...


@dataclass(frozen=True)
class MirrorDraft:
    """The event a task becomes. ``start``/``end`` are aware UTC. Field names follow the calendar lib's draft."""

    subject: str
    start: datetime
    end: datetime
    is_all_day: bool
    body: str = ""
    body_type: str = "text"
    location: str | None = None
    categories: tuple[str, ...] = ()
    reminder_minutes: int | None = None


class MirroredEvent(Protocol):
    id: str
    etag: str | None


class CalendarMirror(Protocol):
    """Shape of the calendar lib's provider, reduced to what the mirror uses. Errors are recognised by class name
    anywhere in their MRO (``NotFound``, ``EtagMismatch``, ``ReconnectRequired``) or by a ``status`` attribute."""

    def create_event(self, draft: MirrorDraft) -> MirroredEvent: ...

    def update_event(self, event_id: str, patch: dict, *, etag: str | None = None) -> MirroredEvent: ...

    def delete_event(self, event_id: str) -> None: ...

    def get_event(self, event_id: str) -> MirroredEvent: ...


class MirrorProviders(Protocol):
    """``for_user`` returns ``(provider name, mirror)`` for the user's live connection, or None when there is none."""

    def for_user(self, session: Any, user_id: str) -> tuple[str, CalendarMirror] | None: ...


@dataclass(frozen=True)
class MirrorPointer:
    """Where a task's external event lives; captured before a hard delete so the event can still be removed."""

    user_id: str
    provider: str | None
    event_id: str
