"""Pure-ASGI middleware: security headers, one DB session per request, CORS with a log line, upload cap.

Add with ``app.add_middleware(Cls, **options)``. The first added is innermost, so the usual order is
``UnhandledErrorMiddleware``, ``UploadLimit``, ``SecurityHeadersMiddleware``, ``LoggingCORSMiddleware``, then the session
middleware last (outermost).
"""

import functools
import logging
from collections.abc import Callable
from typing import Any

import anyio
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import DB_UNAVAILABLE, is_db_unavailable
from .upload_limit import UploadLimit

LOGGER = logging.getLogger(__name__)
__all__ = ["DBSessionMiddleware", "LoggingCORSMiddleware", "SecurityHeadersMiddleware", "UploadLimit",
           "db_session_middleware", "security_headers_middleware"]

DEFAULT_PERMISSIONS_POLICY = "camera=(self), microphone=(self), geolocation=(self)"


class SecurityHeadersMiddleware:
    """App-wide header floor. A route that deliberately set a stricter Referrer-Policy keeps it."""

    def __init__(self, app: ASGIApp, *, permissions_policy: str = DEFAULT_PERMISSIONS_POLICY) -> None:
        self.app = app
        self.permissions_policy = permissions_policy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                if "referrer-policy" not in headers:
                    headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Permissions-Policy"] = self.permissions_policy
                headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_with_headers)


#: ``app.add_middleware(security_headers_middleware)`` reads like the other factories.
security_headers_middleware = SecurityHeadersMiddleware


def _teardown(session: Session) -> None:
    try:
        session.rollback()
    finally:
        session.close()


class DBSessionMiddleware:
    """One session per request on ``request.state.db``; always rolled back and closed afterwards.

    Routes commit for themselves, so whatever is still pending when the request ends (including after an error) is
    discarded. A database that cannot be reached (connection error, pool timeout) is answered 503 ``db_unavailable`` with
    ``Retry-After: 5`` as long as the response has not started. The teardown runs on a worker thread, shielded from
    cancellation, because closing a session is a database round trip.
    """

    def __init__(self, app: ASGIApp, *, session_factory: Callable[[], Session]) -> None:
        self.app, self.session_factory = app, session_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        session = self.session_factory()
        scope.setdefault("state", {})["db"] = session
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except (DBAPIError, PoolTimeoutError) as exc:
            # Only a database that cannot be reached is a retryable 503; a missing table or bad SQL is a bug and propagates.
            if started or not is_db_unavailable(exc):
                raise
            LOGGER.error("database unavailable on %s %s: %s", scope.get("method"), scope.get("path"), exc)
            await JSONResponse(status_code=503, headers={"Retry-After": "5"},
                               content={"detail": DB_UNAVAILABLE})(scope, receive, tracking_send)
        finally:
            try:
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(_teardown, session)
            except Exception:
                LOGGER.warning("request session teardown failed", exc_info=True)


def db_session_middleware(session_factory: Callable[[], Session]) -> Any:
    """``app.add_middleware(db_session_middleware(factory))``."""
    return functools.partial(DBSessionMiddleware, session_factory=session_factory)


class LoggingCORSMiddleware(CORSMiddleware):
    """The stock CORS middleware plus one WARNING per origin it turns away.

    A browser hides a CORS refusal behind "failed to fetch", which looks like a dead backend. Logged origins are capped
    so a scanner sending a new origin each time cannot grow the set or the log.
    """

    MAX_LOGGED = 100

    def __init__(self, app: ASGIApp, allow_origins: Any = (), **kwargs: Any) -> None:
        kwargs.setdefault("allow_methods", ["*"])
        kwargs.setdefault("allow_headers", ["*"])
        kwargs.setdefault("allow_credentials", True)
        origins = [allow_origins] if isinstance(allow_origins, str) else list(allow_origins)
        if kwargs["allow_credentials"] and "*" in origins:
            raise ValueError("allow_origins=['*'] with allow_credentials=True lets any site act as a logged-in user; "
                             "list the origins, or pass allow_credentials=False")
        super().__init__(app, allow_origins=allow_origins, **kwargs)
        self._warned: set[str] = set()

    def is_allowed_origin(self, origin: str) -> bool:
        allowed = super().is_allowed_origin(origin)
        if allowed or origin in self._warned or len(self._warned) > self.MAX_LOGGED:
            return allowed
        if len(self._warned) == self.MAX_LOGGED:
            self._warned.add("")
            LOGGER.warning("CORS: further rejected origins are not logged")
            return allowed
        self._warned.add(origin)
        LOGGER.warning("CORS: origin %s is not allowed, so a browser page served from there cannot call this API; "
                       "add it to the allowed origins", origin)
        return allowed
