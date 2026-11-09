"""COPY AS IS. The Origin rule for every cookie-authenticated state-changing request.

A browser sends the session cookie on its own, so a page on another site could make it DELETE or POST. A request that
carries the access cookie and no bearer token must therefore come from an allowed origin (the API's own or the
redirect allowlist). Bearer requests (phones, scripts) are not ambient and skip it. The sign-in library's own routes
check this themselves and are exempt here.
"""

from __future__ import annotations

from bond_signin.origin import has_bearer, require_origin
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

MUTATING = ("POST", "PUT", "PATCH", "DELETE")
EXEMPT = ("signin", "refresh", "logout", "sessions")  # the library's routes under its prefix


class OriginRule(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        stack = getattr(request.app.state, "signin", None)  # built after the middleware: read at request time
        if (stack is not None and request.method in MUTATING and not request.url.path.startswith(tuple(f"{stack.settings.prefix}/{n}" for n in EXEMPT))
                and request.cookies.get(stack.cookies.access_name) and not has_bearer(request)):
            try:
                require_origin(request, stack.settings)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)
