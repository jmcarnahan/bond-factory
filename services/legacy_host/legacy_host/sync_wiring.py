"""`POST /sync/upload` for an old client: the lib's envelope and dispatcher over `bond_tasks_py.sync_routes`.

An old client writes the LEGACY data keys: `sync_to_calendar` (integer 1/0), `client_ref`, `case_ref`; it never sends
`mirror_enabled`. `adapt` is the whole translation: it widens `reads` with the legacy key (the dispatcher coerces
it by the TABLE column, a Boolean) and renames it to the lib's key before the lib's handler runs. Everything else the
lib already does: server-owned keys are never read, unknown keys are ignored, `prepare` (rules.py) blanks the links.
"""

from __future__ import annotations

from typing import Any

import bond_push_py as push
from bond_sync_py import Ctx, Host, Route, UploadRequest, rejected, upload
from bond_tasks_py import sync_routes, verdict_for
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Request

from . import mirror_wiring, rules
from .deps import current_user
from .models import HOST_COLUMNS, PushDevice, Task, User

LEGACY_KEY = "sync_to_calendar"
LIB_KEY = "mirror_enabled"


def adapt(route: Any) -> Route:
    """The lib's route as the dispatcher's `Route`, taking the legacy key for the mirror flag."""
    handler = route.handler
    reads = route.reads + (LEGACY_KEY,) if LIB_KEY in route.reads else route.reads  # a closing op reads no data

    def legacy_handler(session: Any, ctx: Any, op: Any, data: dict) -> Any:
        if LEGACY_KEY in data:
            data = dict(data)
            flag = data.pop(LEGACY_KEY)
            if flag is not None and LIB_KEY not in data:
                data[LIB_KEY] = flag
        return handler(session, ctx, op, data)

    return Route(route.ops, legacy_handler, reads, route.optional)


def reject_for(session: Any, user: Any, op: Any, exc: Exception) -> Any:
    verdict = verdict_for(exc) or push.verdict_for(exc)  # the task verdict first, then the push one
    return rejected(op.seq, *verdict) if verdict else None


def build_host(app: FastAPI) -> Host:
    def now():
        return app.state.clock.utcnow_naive()

    def user_exists(user_id: str) -> bool:
        with app.state.session_factory() as session:
            return session.get(User, user_id) is not None

    def after_write(ctx: Any, session: Any, task: Any) -> None:
        mirror_wiring.queue(app, ctx, task)

    def after_delete(ctx: Any, session: Any, pointer: Any) -> None:
        pass  # the host's event removal is outside this trait

    routes = sync_routes(Task, now=now, host_columns=HOST_COLUMNS, prepare=rules.prepare, user_exists=user_exists,
                         permissions=rules.LegacyPermissions(lambda uid: _admin(app, uid)),
                         after_write=after_write, after_delete=after_delete)
    host_routes = {key: adapt(route) for key, route in routes.items()}
    for key, device in push.device_routes(PushDevice, now=now).items():  # the device writes its own row: no adapt
        host_routes[key] = Route(device.ops, device.handler, device.reads)
    return Host(routes=host_routes, tables={"tasks": Task.__table__, "push_devices": PushDevice.__table__},
                single_action=frozenset({"tasks", "push_devices"}), reject_for=reject_for)


def _admin(app: FastAPI, user_id: str | None) -> bool:
    with app.state.session_factory() as session:
        return rules.is_admin(session, user_id)


def register(app: FastAPI) -> None:
    mirror_wiring.install(app)
    host = build_host(app)
    router = APIRouter(tags=["sync"])

    @router.post("/sync/upload")
    def upload_route(body: UploadRequest, request: Request, background: BackgroundTasks,
                     user_id: str = Depends(current_user)) -> dict:
        """Always 200 with one verdict per op; an unavailable database is the only escape (503, the client retries)."""
        return upload(request.app.state.session_factory, host, Ctx(user=user_id, background=background), body,
                      now=request.app.state.clock.now).wire()

    app.include_router(router)
