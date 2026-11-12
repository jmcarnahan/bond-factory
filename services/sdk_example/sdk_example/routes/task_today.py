"""The day view and the person's task settings.

    GET /tasks/today     {overdue, today, undated, done_today: [TaskItem], counts: {...}}   query: time_zone
    GET /tasks/settings  {time_zone, start_of_day, end_of_day, lead_minutes, warnings: [], overridden: [names]}
    PUT /tasks/settings  the same fields, each optional; absent = unchanged, null = back to the app default;
                         `warnings` carries the non-blocking notes

The values are the effective ones: what the person stored, else the app's default work day (`SDK_EXAMPLE_START_OF_DAY`,
`_END_OF_DAY`, `_LEAD_MINUTES`). `overridden` names the fields the person stored, so a screen can show "default" for the rest.

Loaded before `tasks.py` so these paths are not read as a task id (see the note there).
"""

from __future__ import annotations

import bond_tasks_py as tasks
from bond_notify_py import dismiss_stale
from bond_tasks_py import SettingsUpdate, settings_item, settings_overridden
from fastapi import Depends, FastAPI, Request

from ..auth_dep import current_user_id
from ..models.notices import Notice
from ..models.task_settings import TaskUserSettings
from ..models.tasks import Task
from ..task_support import check_body, clock_now, items, prefs_of, unit, viewer_zone


def register(app: FastAPI) -> None:
    @app.get("/tasks/today")
    def today(request: Request, time_zone: str | None = None, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            zone = viewer_zone(request, session, user_id, time_zone)
            found = tasks.today(session, task_model=Task, user_id=user_id, now=clock_now(request), viewer_zone=zone)
            return {
                "overdue": items(request, session, found.overdue, zone),
                "today": items(request, session, found.today, zone),
                "undated": items(request, session, found.undated, zone),
                "done_today": items(request, session, found.done_today, zone),
                "counts": dict(found.counts),
            }

    @app.get("/tasks/settings")
    def get_settings(request: Request, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            return settings_item(prefs_of(request, session, user_id), (),
                                 settings_overridden(session.get(TaskUserSettings, user_id)))

    @app.put("/tasks/settings", dependencies=[Depends(check_body)])
    def put_settings(body: SettingsUpdate, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            now = clock_now(request)

            def moved(task, old_due_at) -> None:
                """A date-only task's deadline moved with the work day or zone: its old notices go at once."""
                dismiss_stale(session, Notice, task.id, task.due_at, now)

            prefs, warnings = tasks.update_settings(
                session, settings_model=TaskUserSettings, task_model=Task, user_id=user_id, data=body,
                tz=request.app.state.settings.tz, now=now, on_recomputed=moved,
                defaults=request.app.state.default_prefs)
            return settings_item(prefs, warnings, settings_overridden(session.get(TaskUserSettings, user_id)))
