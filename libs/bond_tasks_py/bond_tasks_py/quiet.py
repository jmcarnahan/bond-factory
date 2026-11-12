"""Quiet hours are derived: after ``end_of_day`` until ``start_of_day`` (neither instant is quiet)."""

from datetime import datetime

from bond_tasks_py.protocols import UserPrefs


def in_quiet_hours(prefs: UserPrefs, zone: str, now: datetime) -> bool:
    """True when ``now`` (naive UTC) is quiet for the user in ``zone``."""
    raise NotImplementedError("quiet.in_quiet_hours is not implemented yet")


def next_work_start(prefs: UserPrefs, zone: str, now: datetime) -> datetime:
    """The next ``start_of_day`` instant after ``now`` as naive UTC."""
    raise NotImplementedError("quiet.next_work_start is not implemented yet")
