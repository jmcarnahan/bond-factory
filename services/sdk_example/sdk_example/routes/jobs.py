"""Fake-mode job control: run every due job as of a supplied time, so a reminder demo needs no real wait.

    POST /jobs/tick {"now": "<ISO 8601>"}   -> {"ran": [{id, job_type, key, status, error, summary, skipped, ...}]}

`now` is optional (the real time when omitted). The scheduling clock is pinned to `now` for the pass and released after.
The frozen clock is app-global: any request that runs during the pass sees `now` too. Any signed-in
user can tick in fake mode. Real mode answers 404: a real deployment runs the worker loop instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

import bond_jobs
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict

from .. import wiring
from ..auth_dep import current_user_id


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
            ran = bond_jobs.tick(state.engine, state.session_factory, state.job_registry, state.clock)
        finally:
            wiring.set_now(request.app, None)
        return {"ran": ran}
