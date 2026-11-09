"""The example's tasks table (the lib's mixin attached to the example Base)."""

from bond_tasks_py import TasksMixin

from ..db import Base


class Task(TasksMixin, Base):
    """Table ``tasks``; owner and assignee ids are plain strings that point at ``users.id`` (no foreign key)."""
