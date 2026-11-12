"""Default wording of a notice."""

from typing import Any

from bond_tasks_py.protocols import UserPrefs


def default_compose(task: Any, stage: str, seq: int, prefs: UserPrefs) -> tuple[str, str]:
    """``(title, body)`` for a stage; the app may pass its own ``Compose``. The title is cut to 255 characters
    and NUL characters are removed from both parts."""
    raise NotImplementedError("compose.default_compose is not implemented yet")
