"""``GET`` and ``PUT /fake/clock``: pin the service clock from a test or a demo, and read it back.

The router is built by the app and mounted only where it wants it. Whether it answers is decided per request by
``enabled()``; this module reads no environment. When ``enabled()`` is false every request to ``/fake/clock`` (any verb,
any body, with or without auth, with or without a trailing slash) answers exactly what an unmounted path answers in the
same app: 404 with the same body, before the body or any dependency is looked at. A production build reveals nothing.

Wire (both verbs answer it): ``{"now": "2026-11-08T10:30:00Z" | null}``. ``PUT`` pins the clock to the instant (an ISO 8601
string; one with no offset is read as UTC); ``null`` or an absent ``now`` releases the pin. A string that is not an ISO
instant (an empty string too), or one outside the range of ``datetime`` once converted to UTC, answers 422
``invalid_now``. When enabled, other verbs answer 405 and ``/fake/clock/`` redirects (307) to ``/fake/clock``.
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict


class PinnableClock(Protocol):
    """What the router needs. ``bond_service_kit.Clock`` already satisfies it."""

    @property
    def frozen(self) -> bool: ...

    def now(self) -> datetime: ...

    def freeze(self, at: datetime) -> None: ...

    def unfreeze(self) -> None: ...


class ClockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    now: str | None = None


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).replace(tzinfo=None).isoformat() + "Z"


def _parse(value: str) -> datetime:
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, {"code": "invalid_now", "message": "now must be an ISO 8601 date and time."}) from None
    try:
        return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)
    except OverflowError:
        raise HTTPException(422, {"code": "invalid_now", "message": "now is outside the supported range."}) from None


_VERBS = ["GET", "PUT", "POST", "DELETE", "PATCH", "HEAD", "OPTIONS"]


def fake_clock_router(clock: PinnableClock, *, enabled: Callable[[], bool],
                      dependencies: Sequence = ()) -> APIRouter:
    """``GET`` / ``PUT /fake/clock`` for ``clock``. ``dependencies`` (``Depends(...)`` items, for example auth) run
    after the ``enabled()`` check. While ``enabled()`` is false the path does not exist: see the module docstring."""

    class GatedRoute(APIRoute):
        def get_route_handler(self):
            inner = super().get_route_handler()

            async def handler(request: Request) -> Response:
                if not enabled():  # before the body is read or any dependency runs
                    raise HTTPException(404, "Not Found")
                return await inner(request)

            return handler

    router = APIRouter(route_class=GatedRoute, dependencies=list(dependencies))

    def view() -> dict:
        return {"now": _iso(clock.now()) if clock.frozen else None}

    @router.get("/fake/clock")
    def get_clock() -> dict:
        return view()

    @router.put("/fake/clock")
    def put_clock(body: ClockBody) -> dict:
        if body.now is not None:
            clock.freeze(_parse(body.now))
        else:
            clock.unfreeze()
        return view()

    @router.api_route("/fake/clock", methods=_VERBS, include_in_schema=False)
    def other_verb() -> Response:
        return Response(status_code=405, headers={"Allow": "GET, PUT"})

    @router.api_route("/fake/clock/", methods=_VERBS, include_in_schema=False)
    def trailing_slash(request: Request) -> Response:
        return RedirectResponse(str(request.url.replace(path=request.url.path.rstrip("/"))), status_code=307)

    return router
