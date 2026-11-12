"""Structural seams the app wires. This lib imports no sibling lib: the real objects come from the app."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Protocol


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


LINK_KIND_CONTACT = "contact"


@dataclass(frozen=True)
class UserPrefs:
    """One user's work day. ``time_zone`` None means the app default. Quiet hours are derived: after
    ``end_of_day`` until ``start_of_day``."""

    time_zone: str | None = None
    start_of_day: time = time(8, 0)
    end_of_day: time = time(17, 0)
    lead_minutes: int = 60


class Preferences(Protocol):
    """Where a user's ``UserPrefs`` come from; ``StoredPreferences`` reads the settings table."""

    def for_user(self, session: Any, user_id: str) -> UserPrefs: ...


class Permissions(Protocol):
    """Who may do what to a task. ``DefaultPermissions`` is today's rule set."""

    def can_edit(self, task: Any, user_id: str) -> bool: ...  # default: owner or assignee

    def can_own(self, task: Any, user_id: str) -> bool: ...  # default: owner (delete, cancel, reassign)

    def can_complete(self, task: Any, user_id: str) -> bool: ...  # default: can_edit


class LinkResolver(Protocol):
    """Labels for stored links and a search for the picker. Link dicts are ``{kind, id, label}``."""

    def labels(self, session: Any, links: list[dict]) -> dict[tuple[str, str], str]: ...

    def search(self, session: Any, user_id: str, kind: str, query: str, limit: int) -> list[dict]: ...


AfterWrite = Callable[[Any, Any], None]  # (session, task), called after flush in create and update
