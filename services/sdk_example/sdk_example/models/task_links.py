"""The link index: one row per (task, kind, ref) so "tasks linked to X" is an indexed join."""

from bond_tasks_py import TaskLinkIndexMixin

from ..db import Base


class TaskLinkIndex(TaskLinkIndexMixin, Base):
    """Table ``task_link_index``."""
