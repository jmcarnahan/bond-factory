"""Functions of the today view, link index and settings group that are not implemented yet.

Whoever implements one deletes its entry here and tests it for real in its own file."""

from datetime import datetime

import pytest
from conftest import Task, UserSettings

import bond_tasks_py as lib
from bond_tasks_py import SettingsUpdate, StoredPreferences

NOW = datetime(2026, 3, 12, 12, 0)

STUBS = {
    "today": lambda: lib.today(None, task_model=Task, user_id="u", now=NOW, viewer_zone="UTC"),
    "retarget_links": lambda: lib.retarget_links(
        None, task_model=Task, index_model=None, kind="contact", old_id="a", new_id="b"),
    "remove_links": lambda: lib.remove_links(None, task_model=Task, index_model=None, kind="contact", ref_id="a"),
    "reindex_links": lambda: lib.reindex_links(None, None, None),
    "make_link_hook": lambda: lib.make_link_hook(None),
    "get_settings": lambda: lib.get_settings(None, UserSettings, "u"),
    "update_settings": lambda: lib.update_settings(
        None, settings_model=UserSettings, task_model=Task, user_id="u", data=SettingsUpdate(), tz="UTC", now=NOW),
    "StoredPreferences.for_user": lambda: StoredPreferences(UserSettings).for_user(None, "u"),
}


@pytest.mark.parametrize("name", sorted(STUBS))
def test_stub_raises_not_implemented(name):
    with pytest.raises(NotImplementedError, match="is not implemented yet"):
        STUBS[name]()
