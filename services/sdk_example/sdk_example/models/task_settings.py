"""Per-user task settings (zone, work day, lead): the lib's mixin attached to the example Base."""

from bond_tasks_py import TaskUserSettingsMixin

from ..db import Base


class TaskUserSettings(TaskUserSettingsMixin, Base):
    """Table ``task_user_settings``; no row means the defaults."""
