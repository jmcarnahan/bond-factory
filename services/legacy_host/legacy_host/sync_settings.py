"""Settings over sync for the legacy host: table `user_prefs` (renamed columns), row id = the user's id.

An existing phone uploads the LEGACY keys (`tz`, `day_start`, `day_end`, `remind_lead`); the lib's keys (`time_zone`,
`start_of_day`, `end_of_day`, `lead_minutes`) work too, and a lib key wins when both are sent. `adapt` is the whole
translation (as `sync_wiring.adapt` is for tasks): it widens `reads` with the legacy names (the dispatcher coerces them
by the TABLE column) and renames them before the lib's handler runs. A null resets that setting to the app default.

    mount(app, routes, tables)   adds the route ("user_prefs", None) and the table; the caller also adds "user_prefs"
                                 to the Host's `single_action`. A refusal is a `TaskError`, which the host's
                                 `reject_for` already maps (the tasks verdict mapper).
"""

from __future__ import annotations

from typing import Any

from bond_sync_py import Route
from bond_tasks_py import settings_routes
from fastapi import FastAPI

from .models import Task, UserPrefs

#: legacy column name -> the lib's key
LEGACY_KEYS = {"tz": "time_zone", "day_start": "start_of_day", "day_end": "end_of_day", "remind_lead": "lead_minutes"}


def adapt(route: Any) -> Route:
    handler = route.handler

    def legacy_handler(session: Any, ctx: Any, op: Any, data: dict) -> Any:
        data = dict(data)
        for legacy, lib in LEGACY_KEYS.items():
            if legacy in data:
                value = data.pop(legacy)
                data.setdefault(lib, value)  # null stays: it is the reset
        return handler(session, ctx, op, data)

    return Route(route.ops, legacy_handler, route.reads + tuple(LEGACY_KEYS), route.optional)


def mount(app: FastAPI, routes: dict, tables: dict) -> None:
    def now():
        return app.state.clock.utcnow_naive()

    for key, route in settings_routes(UserPrefs, Task, now=now).items():
        routes[key] = adapt(route)
    tables[UserPrefs.__tablename__] = UserPrefs.__table__

