"""Fake mode only (404 otherwise): windows into the pretend model and the pretend phone, for tests and the walk.

    GET /fake/push/sent            what the mock Apple sender received: [{token, title, body, collapse_id, data, ...}]
    PUT /fake/capture   {down}     make the pretend model unavailable (true) or available again, to see the degraded path
    GET /fake/clock                {now}: the pinned instant (ISO Z) or null
    PUT /fake/clock {now}          pin the app clock to an ISO instant until set to null; task routes, the sweep and
                                   /jobs/tick (with no `now`) all read it, so a demo's fake clock and the server agree
    PUT /fake/capture/limit {limit}  tighten the per-person parse limit (the walk uses it to reach 429)
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from bond_service_kit import ApiError
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict

from .. import wiring
from ..auth_dep import current_user_id
from ..capture_wiring import RateGuard
from .jobs import parse_now


class DownBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    down: bool


class LimitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int


class ClockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    now: str | None = None


def clock_view(request: Request) -> dict:
    pin = getattr(request.app.state, "clock_pin", None)
    return {"now": pin.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if pin else None}


def fake_only(request: Request) -> None:
    if request.app.state.settings.mode != "fake":
        raise ApiError("not_found", "Not found.", status=404)


def register(app: FastAPI) -> None:
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

    @app.get("/fake/clock")
    def get_clock(request: Request, user_id: str = Depends(current_user_id)) -> dict:
        fake_only(request)
        return clock_view(request)

    @app.put("/fake/clock")
    def put_clock(body: ClockBody, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        fake_only(request)
        pin: datetime | None = parse_now(body.now) if body.now else None
        request.app.state.clock_pin = pin
        wiring.set_now(request.app, pin)
        return clock_view(request)
