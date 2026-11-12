"""Functions of the due-instant, lifecycle and write-path group that are not implemented yet.

Whoever implements one deletes its entry here and tests it for real in its own file."""

from datetime import date, datetime

import pytest
from conftest import Task

import bond_tasks_py as lib
from bond_tasks_py import UserPrefs

NOW = datetime(2026, 3, 12, 12, 0)
PREFS = UserPrefs()


class FakePrefs:
    def for_user(self, session, user_id):
        return PREFS


STUBS = {
    "compute_due_at": lambda: lib.compute_due_at(
        date(2026, 3, 12), None, writer_zone=None, responsible_prefs=PREFS, app_tz="UTC"),
    "recompute_day_due": lambda: lib.recompute_day_due(
        None, task_model=Task, user_id="u", prefs=FakePrefs(), tz="UTC", now=NOW),
    "backfill_due_at": lambda: lib.backfill_due_at(None, task_model=Task, prefs=FakePrefs(), tz="UTC", now=NOW),
    "apply_notice_action": lambda: lib.apply_notice_action(
        None, task=None, action="done", actor_user_id="u", now=NOW),
    "apply_extras": lambda: lib.apply_extras(None, {}, ()),
}


@pytest.mark.parametrize("name", sorted(STUBS))
def test_stub_raises_not_implemented(name):
    with pytest.raises(NotImplementedError, match="is not implemented yet"):
        STUBS[name]()
