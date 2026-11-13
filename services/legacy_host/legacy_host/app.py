"""`create_app(database_url, now=None)`: the legacy host.

The caller is the header `X-User: <id>` (401 without it). Tables are made with `create_all`, which leaves a table
that already exists (a legacy one) alone. `app.state.session_factory` and `app.state.clock` are what tests reach for.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from bond_service_kit import Clock
from bond_storage import GrantUnavailable
from bond_tasks_py import TaskError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from . import models  # noqa: F401  (registers the tables on Base)
from .db import Base, make_engine, make_session_factory
from .routes import router as task_router
from .routes_extra import router as extra_router
from .sync_wiring import register as register_sync
from .wire import legacy_body, legacy_error


def create_app(database_url: str, *, now: Callable[[], datetime] | None = None) -> FastAPI:
    app = FastAPI(title="legacy_host")
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.clock = Clock(source=now)

    @app.exception_handler(TaskError)
    async def task_error(request: Request, exc: TaskError) -> JSONResponse:
        status, body = legacy_error(exc)
        return JSONResponse(status_code=status, content=body)

    @app.exception_handler(GrantUnavailable)
    async def gone(request: Request, exc: GrantUnavailable) -> JSONResponse:
        return JSONResponse(status_code=410, content=legacy_body("share_unavailable", "This link no longer works."))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = str(detail.get("code") or {401: "unauthorized", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "error"))
        message = str(detail.get("message") or exc.detail)
        return JSONResponse(status_code=exc.status_code, content=legacy_body(code, message))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        return JSONResponse(status_code=422, content=legacy_body("invalid_request", str(first.get("msg", "not valid"))))

    app.include_router(task_router)
    app.include_router(extra_router)
    register_sync(app)
    return app
