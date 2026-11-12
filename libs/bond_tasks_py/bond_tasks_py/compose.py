"""Default wording of a notice."""

from typing import Any

from bond_tasks_py.protocols import UserPrefs

TITLE_MAX = 255


def _clean(text: str) -> str:
    return text.replace("\x00", "")


def default_compose(task: Any, stage: str, seq: int, prefs: UserPrefs, *, last: bool = False) -> tuple[str, str]:
    """``(title, body)`` for a stage; the app may pass its own ``Compose``. The title is cut to 255 characters
    and NUL characters are removed from both parts. ``last`` (the final past-due notice) says so in the body.

    A custom ``Compose`` is called with the four seam arguments only and cannot know ``last``: it can compare
    ``seq`` with the ``max_past`` it passes to ``sweep_due``. The notice's ``last`` attribute is set by the sweep
    regardless of the wording."""
    name = _clean(str(getattr(task, "title", "") or ""))
    due_date = getattr(task, "due_date", None)
    due_time = getattr(task, "due_time", None)
    when = ""
    if due_date is not None:
        when = f"{due_date:%b} {due_date.day}" + (f" at {due_time}" if due_time else "")
    if stage == "close":
        prefix, body = "Due soon", f"Due {when}." if when else "Due soon."
    elif stage == "due":
        prefix, body = "Due now", f"Due {when}." if when else "Due now."
    elif seq == 0:
        prefix, body = "Overdue", f"Past its due time ({when})." if when else "Past its due time."
    else:
        prefix = "Overdue"
        body = f"Still overdue, due {when}." if when else "Still overdue."
    if last:
        body += " This is the last reminder; the task stays overdue until it is done or cancelled."
    title = f"{prefix}: {name}" if name else prefix
    return _clean(title)[:TITLE_MAX], _clean(body)
