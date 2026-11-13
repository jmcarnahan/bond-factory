"""The calendar mirror for the legacy host: one in-memory fake provider, a connected `u-owner`, a `draft_for` hook.

    install(app)       sets `app.state.calendar` (the fake), `connected` (user ids with a live connection),
                       `mirror_providers` and `mirror_draft_for`
    queue(ctx, task)   after a write: run `sync_mirror` once the response is out, when the row is `pending`

The host does not own an event's location, categories or reminder after the first push: a person edits them in their
own calendar, so `draft_for` names them in `leave` and the lib's update patch omits them (a create sends all).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import bond_calendar as cal
from bond_tasks_py import sync_mirror
from bond_tasks_py.protocols import MirrorDraft
from fastapi import FastAPI

from .models import Task

#: draft fields the user keeps in their own calendar once the event exists
USER_OWNED = frozenset({"location", "categories", "reminder_minutes"})


class FakeMirror:
    """Adapts the lib's `MirrorDraft` to the calendar lib's draft; patches pass through (the lib builds them)."""

    def __init__(self, provider: cal.FakeCalendarProvider) -> None:
        self.provider = provider

    def create_event(self, draft: MirrorDraft) -> Any:
        return self.provider.create_event(cal.CalendarEventDraft(
            subject=draft.subject, start=draft.start, end=draft.end, is_all_day=draft.is_all_day,
            location=draft.location, body=draft.body, body_type=draft.body_type,
            categories=list(draft.categories), reminder_minutes=draft.reminder_minutes))

    def update_event(self, event_id: str, patch: dict, *, etag: str | None = None) -> Any:
        if "categories" in patch:
            patch = {**patch, "categories": list(patch["categories"] or [])}
        return self.provider.update_event(event_id, patch, etag=etag)

    def delete_event(self, event_id: str) -> None:
        self.provider.delete_event(event_id)

    def get_event(self, event_id: str) -> Any:
        return self.provider.get_event(event_id)


class Providers:
    """`for_user`: the fake calendar for a connected person, else None (the task is `skipped`)."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def for_user(self, session: Any, user_id: str) -> tuple[str, FakeMirror] | None:
        if user_id not in self.app.state.connected:
            return None
        return "fake", FakeMirror(self.app.state.calendar)


def draft_for(session: Any, task: Any, draft: MirrorDraft) -> MirrorDraft:
    return replace(draft, leave=USER_OWNED)


def install(app: FastAPI) -> None:
    app.state.calendar = cal.FakeCalendarProvider(id_prefix="legacy-ev")
    app.state.connected = {"u-owner"}
    app.state.mirror_providers = Providers(app)
    app.state.mirror_draft_for = draft_for


def run_mirror(app: FastAPI, task_id: str) -> None:
    sync_mirror(app.state.session_factory, Task, task_id, app.state.mirror_providers, tz="UTC",
                draft_for=app.state.mirror_draft_for)


def queue(app: FastAPI, ctx: Any, task: Any) -> None:
    if task.mirror_status == "pending" and ctx.background is not None:
        ctx.background.add_task(run_mirror, app, task.id)
