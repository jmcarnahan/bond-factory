"""One error shape for the whole API: ``{"detail": {"code", "message", ...}}``.

A route that raises with a string, an unknown path, a bad method, a rate limit and a body that fails validation all answer in
it. The validation answer lists ``errors`` and never echoes the offending input.
"""

import logging
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

LOGGER = logging.getLogger(__name__)

_CODE_WORD = re.compile(r"^[a-z][a-z0-9_]*$")
_BY_STATUS = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
    409: "conflict", 413: "too_large", 415: "unsupported_media_type", 422: "invalid", 429: "rate_limited",
    500: "internal_error", 501: "not_implemented", 502: "bad_gateway", 503: "unavailable",
}
DB_UNAVAILABLE = {"code": "db_unavailable", "message": "The database is not answering. Try again in a few seconds"}


_SQLITE_UNAVAILABLE = ("unable to open database file", "database is locked")


def is_db_unavailable(exc: BaseException) -> bool:
    """True only for a database that cannot be reached right now, so a retry may help.

    That is: a pool timeout, an invalidated connection, a Postgres SQLSTATE of class 08 (connection), 53 (resources) or
    57P (operator shutdown), or SQLite's "unable to open database file" / "database is locked". Everything else (a missing
    table, a bad statement, a constraint) is a bug and stays a 500: retrying it never helps.
    """
    if isinstance(exc, PoolTimeoutError) or getattr(exc, "connection_invalidated", False):
        return True
    orig = getattr(exc, "orig", None)
    code = str(getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None) or "")
    if code[:2] in ("08", "53") or code.startswith("57P"):
        return True
    return isinstance(exc, OperationalError) and any(m in str(orig or exc).lower() for m in _SQLITE_UNAVAILABLE)


class ApiError(Exception):
    """Raise from a route to answer ``status`` with ``{"detail": {"code", "message", "hint"?, **extra}}``."""

    def __init__(self, code: str, message: str, *, status: int = 400, hint: str | None = None,
                 extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.status, self.hint, self.extra = code, message, status, hint, extra or {}

    def detail(self) -> dict[str, Any]:
        body: dict[str, Any] = {**self.extra, "code": self.code, "message": self.message}
        if self.hint:
            body["hint"] = self.hint
        return body


class RateLimited(Exception):
    """A request was over its limit. Answered 429 with ``Retry-After: 60``."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail


def error_body(status: int, detail: Any) -> dict[str, Any]:
    """``detail`` as ``{code, message, ...}``.

    A dict keeps its fields and gains a missing ``code`` / ``message``. A string that already is a code
    (``invalid_token``) becomes the code, with underscores turned into spaces for the message. Any other string is the
    message and the code falls back by status.
    """
    fallback = _BY_STATUS.get(status, "error")
    if isinstance(detail, dict):
        code = str(detail.get("code") or fallback)
        return {**detail, "code": code, "message": str(detail.get("message") or code.replace("_", " "))}
    text = str(detail)
    if _CODE_WORD.match(text):
        return {"code": text, "message": text.replace("_", " ")}
    return {"code": fallback, "message": text}


def _detail(status: int, detail: Any, legacy: bool) -> Any:
    """The ``detail`` member: the object form, or (legacy flag) a string detail left as the string it was."""
    if legacy and not isinstance(detail, dict):
        return str(detail)
    return error_body(status, detail)


def _validation_body(exc: RequestValidationError) -> dict[str, Any]:
    errors = [
        {"loc": [p if isinstance(p, (int, str)) else str(p) for p in e.get("loc", ())],
         "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
        for e in exc.errors()
    ]
    where = ".".join(str(p) for p in errors[0]["loc"] if p != "body") if errors else ""
    if errors:
        message = f"{where}: {errors[0]['msg']}" if where else errors[0]["msg"]
    else:
        message = "The request is not valid"
    return {"code": "validation_error", "message": message, "errors": errors}


def install_error_handlers(app: FastAPI, *, legacy_detail_string: bool = False) -> None:
    """Register the handlers. ``legacy_detail_string=True`` keeps ``{"detail": "<string>"}`` for string details."""

    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail()})

    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content={"detail": _detail(exc.status_code, exc.detail, legacy_detail_string)},
                            headers=getattr(exc, "headers", None))

    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _validation_body(exc)})

    async def rate_limited(request: Request, exc: RateLimited) -> JSONResponse:
        message = f"Rate limit exceeded: {exc.detail}" if exc.detail else "Rate limit exceeded"
        return JSONResponse(status_code=429, content={"detail": {"code": "rate_limited", "message": message}},
                            headers={"Retry-After": "60"})

    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return _internal_error(legacy_detail_string)

    app.add_exception_handler(ApiError, api_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimited, rate_limited)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled)


def _internal_error(legacy: bool) -> JSONResponse:
    if legacy:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    return JSONResponse(status_code=500, content={"detail": {"code": "internal_error",
                                                             "message": "Something went wrong on our side"}})


class UnhandledErrorMiddleware:
    """Catch-all 500 (and pool-timeout 503) placed INSIDE CORS.

    Starlette runs the ``Exception`` handler in ``ServerErrorMiddleware``, outside every user middleware, so its answer
    carries no CORS headers and a browser reports a network error instead of the 500. Add this middleware first (innermost)
    so the answer stays inside the CORS wrapper.
    """

    def __init__(self, app: ASGIApp, *, legacy_detail_string: bool = False) -> None:
        self.app = app
        self.legacy = legacy_detail_string

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message: Any) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            unavailable = is_db_unavailable(exc)
            if unavailable:
                LOGGER.error("database unavailable on %s %s: %s", scope.get("method"), scope.get("path"), exc)
            else:
                LOGGER.exception("Unhandled exception on %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            if unavailable:
                await JSONResponse(status_code=503, headers={"Retry-After": "5"},
                                   content={"detail": DB_UNAVAILABLE})(scope, receive, send)
            else:
                await _internal_error(self.legacy)(scope, receive, send)
