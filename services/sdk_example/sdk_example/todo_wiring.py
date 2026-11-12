"""Wires the TODO checklist libraries into the example: preferences, links, inbox, push, capture.

`install(app)` is idempotent and puts these on `app.state`:

    todo_prefs     `StoredPreferences` over the settings table (the default `Preferences`)
    contacts       `FakeContacts`: the `LinkResolver` and the capture `EntityResolver`
    link_hook      the `after_write` hook that keeps the link index in step
    push_sender    `MockSender` in fake mode (read back by `GET /fake/push/sent`); in real mode an `ApnsSender`
                   when SDK_EXAMPLE_APNS_KEY_FILE, _KEY_ID and _TEAM_ID are all set, else None (no push channel)
    capture_llm    `ReplayLlm` in fake mode, None in real mode (every parse then degrades)
    capture_guard  `RateGuard`;   accepted_events  the demo stub's `EventLog`

`dismiss` and `after_task_write` are the one place a task change reaches the inbox, used by REST and sync alike.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from bond_notify_py import dismiss_for_source, dismiss_stale
from bond_push_py import ApnsSender, MockSender
from bond_tasks_py import StoredPreferences, make_link_hook, notice_recipients
from bond_tasks_py.models import TaskStatus
from fastapi import FastAPI

from .capture_wiring import EventLog, RateGuard, ReplayLlm
from .contacts import FakeContacts
from .models.notices import Notice
from .models.task_links import TaskLinkIndex
from .models.task_settings import TaskUserSettings
from .models.tasks import Task


def apns_sender() -> ApnsSender | None:
    """Real mode only: an APNs sender when the three variables are set. The key text stays in its file."""
    path, key_id, team = (os.environ.get(n, "") for n in
                          ("SDK_EXAMPLE_APNS_KEY_FILE", "SDK_EXAMPLE_APNS_KEY_ID", "SDK_EXAMPLE_APNS_TEAM_ID"))
    if not (path and key_id and team):
        return None
    return ApnsSender(Path(path).read_text(), key_id, team)


def install(app: FastAPI) -> None:
    if getattr(app.state, "todo_prefs", None) is not None:
        return
    fake = app.state.settings.mode == "fake"
    app.state.todo_prefs = StoredPreferences(TaskUserSettings)
    app.state.contacts = FakeContacts()
    app.state.link_hook = make_link_hook(TaskLinkIndex)
    app.state.push_sender = MockSender() if fake else apns_sender()
    app.state.capture_llm = ReplayLlm() if fake else None
    app.state.capture_guard = RateGuard()
    app.state.accepted_events = EventLog()


def after_task_write(session: Any, task: Any, now: datetime) -> None:
    """After any task write (REST or sync): a finished task's notices are put away, and an open task's notices made
    for another due instant are put away too (`dismiss_stale` leaves the current deadline's alone)."""
    if task.status != TaskStatus.OPEN.value:
        dismiss_for_source(session, Notice, task.id, now)
    else:
        dismiss_stale(session, Notice, task.id, task.due_at, now)


def after_task_delete(session: Any, task_id: str, now: datetime) -> None:
    dismiss_for_source(session, Notice, task_id, now)


def recipients_of(session: Any, task_id: str) -> set[str]:
    """Who gets this task's notices now (owner and assignee); empty when the task is new or gone. Take it BEFORE a
    write that can reassign, then pass it to `dismiss_for_those_who_left` after."""
    task = session.get(Task, task_id)
    return set(notice_recipients(task)) if task is not None else set()


def dismiss_for_those_who_left(session: Any, task: Any, before: set[str], now: datetime) -> None:
    """A person who is no longer owner or assignee keeps no live notice of the task; the others keep theirs."""
    left = before - set(notice_recipients(task))
    if left:
        dismiss_for_source(session, Notice, task.id, now, user_ids=left)
