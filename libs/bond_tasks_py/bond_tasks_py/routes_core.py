"""What the router factory's handlers share: the viewer's zone, the wire items, the keyword arguments of a write.

No web framework is imported here. ``routes.py`` builds one ``Core`` per router and every handler goes through it.
"""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from bond_tasks_py.due import valid_zone
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import Permissions, UserPrefs
from bond_tasks_py.queries import viewer_today
from bond_tasks_py.serialize import task_items
from bond_tasks_py.stages import effective_zone
from bond_tasks_py.usersettings import StoredPreferences, get_settings


@dataclass(frozen=True)
class Core:
    """The factory's arguments plus the rules that read them. ``session`` is passed to every method."""

    task_model: Any
    settings_model: Any
    link_index_model: Any
    session_scope: Callable[[], AbstractContextManager[Any]]
    now: Callable[[], datetime]
    zone_for: Callable[[str], str | None] | None
    tz: str
    permissions: Permissions | None
    prepare: Any
    item_extras: Callable[[Any], Mapping[str, Any]] | None
    labels: Callable[[Any, list[dict]], Mapping[tuple[str, str], str]] | None
    names: Callable[[Any, list[str]], dict[str, str]] | None
    user_exists: Callable[[Any, str], bool] | None
    prefs: Any
    defaults: UserPrefs | None
    link_hook: Callable[[Any, Any], None] | None
    after_write: Callable[..., None] | None
    snapshot: Callable[[Any, str], Any] | None
    after_commit: Callable[[Any, Any], None] | None

    def stored_prefs(self, session: Any, user_id: str) -> UserPrefs:
        """The person's effective work day: what they stored over the app defaults (the defaults alone with no table)."""
        if self.settings_model is None:
            return self.defaults or UserPrefs()
        return get_settings(session, self.settings_model, user_id, self.defaults)

    def stored_zone(self, session: Any, user_id: str) -> str | None:
        zone = self.stored_prefs(session, user_id).time_zone
        if not zone and self.zone_for is not None:
            zone = self.zone_for(user_id)
        return zone

    def viewer_zone(self, session: Any, user_id: str, asked: str | None = None) -> str:
        """The ``time_zone`` asked for, else the person's stored zone, else the factory's ``tz``."""
        if asked:
            if not valid_zone(asked):
                raise TaskError("invalid_time_zone", "That is not a time zone name.", 422)
            return asked
        return effective_zone(replace(UserPrefs(), time_zone=self.stored_zone(session, user_id)), self.tz)

    def items(self, session: Any, rows: Sequence[Any], zone: str) -> list[dict]:
        now = self.now()
        return task_items(
            list(rows), today=viewer_today(now, zone), now=now,
            names=(lambda ids: self.names(session, ids)) if self.names is not None else None,
            labels=(lambda links: self.labels(session, links)) if self.labels is not None else None,
            extras=self.item_extras)

    def item(self, session: Any, task: Any, zone: str) -> dict:
        return self.items(session, [task], zone)[0]

    def write_kwargs(self, session: Any, user_id: str) -> dict:
        """The keyword arguments ``create`` and ``update`` take beyond the data."""
        prefs = self.prefs
        if prefs is None and self.settings_model is not None:
            prefs = StoredPreferences(self.settings_model, self.defaults)
        exists = self.user_exists
        return {"now": self.now(), "tz": self.tz, "writer_zone": self.stored_zone(session, user_id), "prefs": prefs,
                "user_exists": (lambda uid: exists(session, uid)) if exists is not None else None,
                "after_write": self.link_hook, "prepare": self.prepare}

    def written(self, session: Any, background: Any, task: Any, before: Any = None) -> None:
        """After a write, inside the transaction: the host's hook, then its after-commit queue."""
        if self.after_write is not None:
            self.after_write(session, task, self.now(), before)
        if self.after_commit is not None:
            self.after_commit(background, task)

    def before(self, session: Any, task_id: str) -> Any:
        return self.snapshot(session, task_id) if self.snapshot is not None else None


def check_body_fields(body: Any) -> None:
    """The two body errors that get their own codes: priority is 1 to 3 (or null); ``time_zone`` is an IANA name."""
    if not isinstance(body, dict):
        return
    priority = body.get("priority")
    if priority is not None and (isinstance(priority, bool) or priority not in (1, 2, 3)):
        raise TaskError("invalid_priority", "Priority is 1, 2 or 3.", 422)
    zone = body.get("time_zone")
    if zone is not None and not (isinstance(zone, str) and valid_zone(zone)):
        raise TaskError("invalid_time_zone", "That is not a time zone name.", 422)


def checked_answer(error_map: Callable[[Any], Any], exc: Any) -> tuple[int, Any]:
    """``error_map(exc)`` must return ``(status, body)``: an int status and a JSON body. Anything else (or a raise)
    is a ``TypeError`` that names ``error_map``, so the 500 says what to fix."""
    try:
        answer = error_map(exc)
    except Exception as err:
        raise TypeError(f"error_map raised {type(err).__name__}: {err}") from err
    if (not isinstance(answer, tuple) or len(answer) != 2 or isinstance(answer[0], bool)
            or not isinstance(answer[0], int)):
        raise TypeError(f"error_map must return (status: int, body), got {answer!r}")
    return answer
