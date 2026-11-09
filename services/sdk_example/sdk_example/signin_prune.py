"""COPY AS IS. Housekeeping job: delete spent hand-off codes and dead refresh-session rows.

`schedule` runs from the job tick's `before` hook (routes/jobs.py in fake mode; an app's worker loop passes the same
hook) and enqueues ONE `signin_prune` job per UTC day, due at the next midnight. The handler calls the two libraries'
`prune`. An app with its own scheduler enqueues the job there instead.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bond_jobs
from fastapi import FastAPI

from .models.jobs import BackgroundJob

JOB_TYPE = "signin_prune"


def _epoch(moment: datetime) -> float:
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).timestamp()


def schedule(session: Any, now: datetime) -> None:
    day = now.date()
    due = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    bond_jobs.enqueue(session, BackgroundJob, JOB_TYPE, {}, run_at=due, key=f"{JOB_TYPE}:{day}", now=now)


def install(app: FastAPI) -> None:
    @app.state.job_registry.handler(JOB_TYPE)
    def signin_prune(session: Any, payload: dict, now: datetime) -> dict:
        stack = app.state.signin
        handoffs = stack.handoffs.prune(session, now=_epoch(now))
        sessions = stack.sessions.prune(session, now=_epoch(now))
        return {"summary": f"pruned {handoffs} hand-offs, {sessions} sessions"}
