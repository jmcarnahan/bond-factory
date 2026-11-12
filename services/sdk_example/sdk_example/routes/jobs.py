"""Fake-mode time travel: run the notice sweep and every due job as of a supplied time, so a demo needs no real wait.

    POST /jobs/tick {"now": "<ISO 8601>"}
        -> {"ran": [{id, job_type, key, status, error, summary, skipped, ...}],
            "sweep": {claimed, skipped, queued, repaired, errors}, "deliver": {leased, sent, ...}}

The sweep claims the notices that are due (inbox rows and push outbox rows); pushes then go to the mock sender
(`GET /fake/push/sent`). A real deployment runs the same two steps from its worker loop: `sweep_wiring.before_hook` as the
`before` hook of `bond_jobs.tick` (with `before_every`), or `scripts/sweep_interval.py` when it has no jobs table.

`now` is optional (the pinned or real time when omitted). The scheduling clock is pinned to `now` for the pass;
afterwards it returns to the pin set by `PUT /fake/clock`, or, when nothing is pinned, the clock is RELEASED to real
time (a tick with a `now` does not leave the app on that instant).
The frozen clock is app-global: any request that runs during the pass sees `now` too. Any signed-in
user can tick in fake mode. Real mode answers 404: a real deployment runs the worker loop instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

import bond_jobs
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict

from .. import sweep_wiring, wiring
from ..auth_dep import current_user_id
from ..signin_prune import schedule as schedule_prune


class TickBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    now: str | None = None


def parse_now(value: str) -> datetime:
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        raise ApiError("invalid_now", "now must be an ISO 8601 date and time.", status=422) from None
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def register(app: FastAPI) -> None:
    @app.post("/jobs/tick")
    def tick(request: Request, body: TickBody | None = None, user_id: str = Depends(current_user_id)) -> dict:
        state = request.app.state
        if state.settings.mode != "fake":
            raise ApiError("not_found", "Not found.", status=404)
        if body is not None and body.now:
            wiring.set_now(request.app, parse_now(body.now))
        try:
            swept = sweep_wiring.sweep_app(request.app, state.clock.utcnow_naive())
            ran = bond_jobs.tick(state.engine, state.session_factory, state.job_registry, state.clock,
                                 before=schedule_prune)  # an app's worker loop passes sweep_wiring.before_hook
        finally:
            wiring.set_now(request.app, getattr(state, "clock_pin", None))  # the pin, else real time
        return {"ran": ran, **swept}
