"""App columns on the tasks table: the app validates, bond only stores what the allow-list names."""

from collections.abc import Collection, Mapping
from typing import Any


def apply_extras(task: Any, extras: Mapping[str, Any] | None, host_columns: Collection[str]) -> None:
    """Set each ``extras`` key that is named in ``host_columns`` on the task. Keys outside the allow-list are ignored
    (a device may send more than the app stores). A name in ``host_columns`` that the task has no column for is a
    programming error and raises ``ValueError``, even when ``extras`` does not carry it."""
    for name in host_columns:
        if not hasattr(type(task), name):
            raise ValueError(f"host column {name!r} is not a column of {type(task).__name__}")
    for name, value in (extras or {}).items():
        if name in host_columns:
            setattr(task, name, value)
