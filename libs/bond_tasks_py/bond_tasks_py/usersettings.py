"""Per-user task settings: the ``task_user_settings`` mixin, the settings services and the default ``Preferences``.

No row means defaults. Two times define the work day; quiet hours are derived (after ``end_of_day`` until
``start_of_day``), so there are no quiet-hours columns.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Integer, String

from bond_tasks_py.protocols import UserPrefs
from bond_tasks_py.settings_schema import SettingsUpdate
from bond_tasks_py.timeutil import utcnow

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


def get_settings(session: Any, settings_model: Any, user_id: str) -> UserPrefs:
    """The user's stored preferences, or the defaults when there is no row."""
    raise NotImplementedError("usersettings.get_settings is not implemented yet")


def update_settings(session: Any, *, settings_model: Any, task_model: Any, user_id: str, data: SettingsUpdate,
                    tz: str, now: datetime) -> tuple[UserPrefs, list[str]]:
    """Upsert the row, recompute date-only due instants in the same transaction, return prefs and warnings."""
    raise NotImplementedError("usersettings.update_settings is not implemented yet")


class StoredPreferences:
    """The default ``Preferences``: reads ``settings_model``."""

    def __init__(self, settings_model: Any) -> None:
        self.settings_model = settings_model

    def for_user(self, session: Any, user_id: str) -> UserPrefs:
        raise NotImplementedError("usersettings.StoredPreferences.for_user is not implemented yet")
