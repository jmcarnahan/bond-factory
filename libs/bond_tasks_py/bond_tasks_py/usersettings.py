"""Per-user task settings: the ``task_user_settings`` mixin, the settings services and the default ``Preferences``.

No row means defaults, and a NULL column means "follow the app default": the app passes its own ``defaults``
(``UserPrefs``) to ``get_settings`` / ``StoredPreferences`` / ``update_settings``; None keeps the lib constants. Two
times define the work day; quiet hours are derived (after ``end_of_day`` until ``start_of_day``), so there are no
quiet-hours columns.
"""

from collections.abc import Callable
from datetime import datetime, time
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String

from bond_tasks_py import due
from bond_tasks_py.errors import TaskError
from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.settings_schema import SettingsUpdate
from bond_tasks_py.timeutil import parse_hhmm, to_naive_utc, utcnow

#: column name -> nullable. The literal contract of ``task_user_settings``; tests pin it.
TASK_USER_SETTINGS_COLUMNS: dict[str, bool] = {
    "user_id": False,
    "time_zone": True,
    "start_of_day": True,
    "end_of_day": True,
    "lead_minutes": True,
    "updated_at": False,
}


class TaskUserSettingsMixin:
    __tablename__ = "task_user_settings"

    user_id = Column(String, primary_key=True)  # no foreign key
    # NULL in any of the next four = the user set nothing: the app default applies (and the field is not "overridden")
    time_zone = Column(String(64), nullable=True)  # IANA name
    start_of_day = Column(String(5), nullable=True)  # local "HH:MM"
    end_of_day = Column(String(5), nullable=True)
    lead_minutes = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow)


_FIELDS = ("time_zone", "start_of_day", "end_of_day", "lead_minutes")


def _prefs(row: Any, defaults: UserPrefs | None = None) -> UserPrefs:
    """The effective preferences: each stored (non-NULL) column, else the matching field of ``defaults``."""
    base = defaults or UserPrefs()
    return UserPrefs(
        time_zone=base.time_zone if row.time_zone is None else row.time_zone,
        start_of_day=base.start_of_day if row.start_of_day is None else parse_hhmm(row.start_of_day),
        end_of_day=base.end_of_day if row.end_of_day is None else parse_hhmm(row.end_of_day),
        lead_minutes=base.lead_minutes if row.lead_minutes is None else row.lead_minutes)


def settings_overridden(row: Any) -> list[str]:
    """The fields the user has stored (non-NULL), in the order time_zone, start_of_day, end_of_day, lead_minutes.
    ``row`` may be None (no row: nothing is overridden). A settings screen shows the rest as "default"."""
    return [] if row is None else [name for name in _FIELDS if getattr(row, name) is not None]


def get_settings(session: Any, settings_model: Any, user_id: str, defaults: UserPrefs | None = None) -> UserPrefs:
    """The user's effective preferences: the stored fields over ``defaults`` (None = the lib constants). With no
    row, ``defaults`` itself."""
    row = session.get(settings_model, user_id)
    return (defaults or UserPrefs()) if row is None else _prefs(row, defaults)


def _work_day_minutes(a: time, b: time) -> int:
    return ((b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)) % 1440


def update_settings(session: Any, *, settings_model: Any, task_model: Any, user_id: str, data: SettingsUpdate,
                    tz: str, now: datetime, on_recomputed: Callable[[Any, datetime | None], None] | None = None,
                    defaults: UserPrefs | None = None) -> tuple[UserPrefs, list[str]]:
    """Upsert the row, recompute date-only due instants in the same transaction, return prefs and warnings.

    Only the fields sent change. A field sent as null is reset: NULL is stored and the ``defaults`` (None = the lib
    constants) apply again; ``settings_overridden(row)`` lists what the user still has set. The effective work day
    is what is checked and compared, so a reset that changes the effective end of day or zone recomputes the due
    instants too. An unknown zone is ``invalid_time_zone``; equal start and end is
    ``invalid_work_day``; a work day across midnight is fine. Changing ``end_of_day`` or ``time_zone`` moves the
    ``due_at`` of the user's open date-only tasks (``tz`` is the app default zone for a user with none stored).
    ``on_recomputed(task, old_due_at)`` (optional) is called once per task whose ``due_at`` really changed, after
    the flush, so a host can put away the stale notices (``dismiss_stale``).
    Warnings never block the write: ``lead_longer_than_work_day``, and ``time_zone_unknown`` when the work day
    changed while the user has no stored zone (their date-only tasks then follow the app default zone)."""
    sent = data.model_fields_set
    if "time_zone" in sent and data.time_zone is not None and not due.valid_zone(data.time_zone):
        raise TaskError("invalid_time_zone")
    row = session.get(settings_model, user_id)
    before = _prefs(row, defaults) if row is not None else (defaults or UserPrefs())
    values = {name: getattr(data, name) if name in sent else (getattr(row, name) if row is not None else None)
              for name in _FIELDS}  # stored values; None = follow the default
    effective = _prefs(SimpleNamespace(**values), defaults)
    if effective.start_of_day == effective.end_of_day:
        raise TaskError("invalid_work_day", "The work day needs different start and end times.", 422)
    if row is None:
        row = settings_model(user_id=user_id)
        session.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    row.updated_at = to_naive_utc(now)
    session.flush()
    prefs = _prefs(row, defaults)
    if prefs.end_of_day != before.end_of_day or prefs.time_zone != before.time_zone:
        due.recompute_day_due(session, task_model=task_model, user_id=user_id,
                              prefs=StoredPreferences(settings_model, defaults), tz=tz, now=now,
                              on_recomputed=on_recomputed)
    warnings = []
    day_changed = (prefs.start_of_day, prefs.end_of_day) != (before.start_of_day, before.end_of_day)
    if day_changed and prefs.time_zone is None:
        warnings.append("time_zone_unknown")  # date-only instants use the app default zone until a zone is stored
    if prefs.lead_minutes > _work_day_minutes(prefs.start_of_day, prefs.end_of_day):
        warnings.append("lead_longer_than_work_day")
    return prefs, warnings


class StoredPreferences:
    """The default ``Preferences``: reads ``settings_model``; ``defaults`` (None = the lib constants) fills what a
    user has not set and answers for a user with no row."""

    def __init__(self, settings_model: Any, defaults: UserPrefs | None = None) -> None:
        self.settings_model = settings_model
        self.defaults = defaults

    def for_user(self, session: Any, user_id: str) -> UserPrefs:
        return get_settings(session, self.settings_model, user_id, self.defaults)
