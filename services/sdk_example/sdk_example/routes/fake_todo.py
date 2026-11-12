"""Fake mode only (404 otherwise): windows into the pretend model and the pretend phone, for tests and the walk.

    GET /fake/push/sent            what the mock Apple sender received: [{token, title, body, collapse_id, data, ...}]
    PUT /fake/capture   {down}     make the pretend model unavailable (true) or available again, to see the degraded path
    GET /fake/clock                {now}: the pinned instant (ISO Z) or null        (the kit's `fake_clock_router`)
    PUT /fake/clock {now}          pin the app clock to an ISO instant until set to null; task routes, the sweep, the sync
                                   upload's `server_now` and /jobs/tick (with no `now`) all read it, so a demo's fake clock
                                   and the server agree. 404 unless fake mode; needs a session.
    PUT /fake/capture/limit {limit}  tighten the per-person parse limit (the walk uses it to reach 429)
"""

from __future__ import annotations

from dataclasses import asdict

from bond_service_kit import ApiError, fake_clock_router
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict

from ..auth_dep import current_user_id
from ..capture_wiring import RateGuard
from ..clock_pin import RoutePin


class DownBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    down: bool


class LimitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int


def fake_only(request: Request) -> None:
    if request.app.state.settings.mode != "fake":
        raise ApiError("not_found", "Not found.", status=404)


def register(app: FastAPI) -> None:
    app.include_router(fake_clock_router(RoutePin(app), enabled=lambda: app.state.settings.mode == "fake",
                                         dependencies=[Depends(current_user_id)]))

    @app.get("/fake/push/sent")
    def push_sent(request: Request, user_id: str = Depends(current_user_id)) -> dict:
        fake_only(request)
        sender = request.app.state.push_sender
        return {"items": [] if sender is None else [
            {**asdict(m), "expires_at": m.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ") if m.expires_at else None}
            for m in sender.sent]}

    @app.put("/fake/capture")
    def capture_switch(body: DownBody, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        fake_only(request)
        request.app.state.capture_llm.down = body.down
        return {"down": body.down}

    @app.put("/fake/capture/limit")
    def capture_limit(body: LimitBody, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        fake_only(request)
        request.app.state.capture_guard = RateGuard(limit=max(body.limit, 0))
        return {"limit": body.limit}
