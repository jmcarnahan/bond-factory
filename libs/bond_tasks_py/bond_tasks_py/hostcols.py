"""App columns on the tasks table: the app validates, bond only stores what the allow-list names."""

from collections.abc import Mapping, Sequence
from typing import Any


def apply_extras(task: Any, extras: Mapping[str, Any] | None, host_columns: Sequence[str]) -> None:
    """Set each ``extras`` key that is in ``host_columns`` on the task; a key outside it raises."""
    raise NotImplementedError("hostcols.apply_extras is not implemented yet")
