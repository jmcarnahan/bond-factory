"""Functions of the stage, sweep, outbox and retention group that are not implemented yet.

Whoever implements one deletes its entry here and tests it for real in its own file."""

from datetime import datetime

import pytest
from conftest import Ledger, Outbox, Task

import bond_tasks_py as lib
from bond_tasks_py import UserPrefs

NOW = datetime(2026, 3, 12, 12, 0)
PREFS = UserPrefs()


class FakePrefs:
    def for_user(self, session, user_id):
        return PREFS


STUBS = {
    "deadline_token": lambda: lib.deadline_token(None),
    "current_stage": lambda: lib.current_stage(None, PREFS, "UTC", NOW),
    "stage_times": lambda: lib.stage_times(None, PREFS, "UTC", NOW),
    "in_quiet_hours": lambda: lib.in_quiet_hours(PREFS, "UTC", NOW),
    "next_work_start": lambda: lib.next_work_start(PREFS, "UTC", NOW),
    "sweep_due": lambda: lib.sweep_due(None, task_model=Task, ledger_model=Ledger, now=NOW, prefs=FakePrefs()),
    "deliver_pending": lambda: lib.deliver_pending(
        None, ledger_model=Ledger, outbox_model=Outbox, notifiers={}, now=NOW, commit=lambda: None),
    "prune_ledger": lambda: lib.prune_ledger(
        None, task_model=Task, ledger_model=Ledger, outbox_model=Outbox, now=NOW),
    "default_compose": lambda: lib.default_compose(None, "due", 0, PREFS),
}


@pytest.mark.parametrize("name", sorted(STUBS))
def test_stub_raises_not_implemented(name):
    with pytest.raises(NotImplementedError, match="is not implemented yet"):
        STUBS[name]()
