"""Per-user task settings: the ``task_user_settings`` mixin, the settings services and the default ``Preferences``.

No row means defaults. Two times define the work day; quiet hours are derived (after ``end_of_day`` until
``start_of_day``), so there are no quiet-hours columns.
"""

from collections.abc import Callable
from datetime import datetime
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
    "start_of_day": False,
    "end_of_day": False,
    "lead_minutes": False,
    "updated_at": False,
}


class TaskUserSettingsMixin:
    __tablename__ = "task_user_settings"

    user_id = Column(String, primary_key=True)  # no foreign key
    time_zone = Column(String(64), nullable=True)  # IANA name; None = the app default
    start_of_day = Column(String(5), nullable=False, default="08:00")  # local "HH:MM"
    end_of_day = Column(String(5), nullable=False, default="17:00")
    lead_minutes = Column(Integer, nullable=False, default=60)
    updated_at = Column(DateTime, nullable=False, default=utcnow)


def _prefs(row: Any) -> UserPrefs:
    return UserPrefs(time_zone=row.time_zone, start_of_day=parse_hhmm(row.start_of_day),
                     end_of_day=parse_hhmm(row.end_of_day), lead_minutes=row.lead_minutes)


def get_settings(session: Any, settings_model: Any, user_id: str) -> UserPrefs:
    """The user's stored preferences, or the defaults when there is no row."""
    row = session.get(settings_model, user_id)
    return UserPrefs() if row is None else _prefs(row)


def _work_day_minutes(start: str, end: str) -> int:
    a, b = parse_hhmm(start), parse_hhmm(end)
    return ((b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)) % 1440


def update_settings(session: Any, *, settings_model: Any, task_model: Any, user_id: str, data: SettingsUpdate,
                    tz: str, now: datetime,
                    on_recomputed: Callable[[Any, datetime | None], None] | None = None) -> tuple[UserPrefs, list[str]]:
    """Upsert the row, recompute date-only due instants in the same transaction, return prefs and warnings.

    Only the fields sent change. An unknown zone is ``invalid_time_zone``; equal start and end is
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
    before = _prefs(row) if row is not None else UserPrefs()
    values = {
        "time_zone": data.time_zone if "time_zone" in sent else before.time_zone,
        "start_of_day": data.start_of_day if data.start_of_day is not None else before.start_of_day.strftime("%H:%M"),
        "end_of_day": data.end_of_day if data.end_of_day is not None else before.end_of_day.strftime("%H:%M"),
        "lead_minutes": data.lead_minutes if data.lead_minutes is not None else before.lead_minutes,
    }
    if parse_hhmm(values["start_of_day"]) == parse_hhmm(values["end_of_day"]):
        raise TaskError("invalid_work_day", "The work day needs different start and end times.", 422)
    if row is None:
        row = settings_model(user_id=user_id)
        session.add(row)
    for name, value in values.items():
        setattr(row, name, value)
    row.updated_at = to_naive_utc(now)
    session.flush()
    prefs = _prefs(row)
    if prefs.end_of_day != before.end_of_day or prefs.time_zone != before.time_zone:
        due.recompute_day_due(session, task_model=task_model, user_id=user_id,
                              prefs=StoredPreferences(settings_model), tz=tz, now=now,
                              on_recomputed=on_recomputed)
    warnings = []
    day_changed = (prefs.start_of_day, prefs.end_of_day) != (before.start_of_day, before.end_of_day)
    if day_changed and prefs.time_zone is None:
        warnings.append("time_zone_unknown")  # date-only instants use the app default zone until a zone is stored
    if prefs.lead_minutes > _work_day_minutes(values["start_of_day"], values["end_of_day"]):
        warnings.append("lead_longer_than_work_day")
    return prefs, warnings


class StoredPreferences:
    """The default ``Preferences``: reads ``settings_model``."""

    def __init__(self, settings_model: Any) -> None:
        self.settings_model = settings_model

    def for_user(self, session: Any, user_id: str) -> UserPrefs:
        return get_settings(session, self.settings_model, user_id)
