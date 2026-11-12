"""Natural-language capture and the link search.

    POST /tasks/parse           {text, today?, time_zone?, rich?} -> {items: [TaskCandidate | EventCandidate], degraded, reason}
                                `rich: true` also asks for location, notes, duration and attendees (default false: the
                                answer is unchanged); creates nothing; 429 `capture_denied` when the guard refuses; 422 `text_required` or
                                `text_too_long`. No model (real mode without a vendor client, or the fake switch)
                                gives one degraded task draft, never an error.
    GET  /tasks/links/search    ?kind=contact&q=sam -> {items: [{kind, id, label}]}
    POST /capture/events        an accepted EventCandidate; the demo's stand-in for "create a calendar event" (in memory,
                                fake mode only: 404 otherwise, like the rest of the stub)
    GET  /capture/events        the caller's accepted events

Loaded before `tasks.py` so these paths are not read as a task id (see the note there).
"""

from __future__ import annotations

from datetime import date

import bond_tasks_py as tasks
from bond_capture_py import CaptureError, parse_capture
from bond_service_kit import ApiError
from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth_dep import current_user_id
from ..task_support import clock_now, prefs_of, unit, viewer_zone
from .fake_todo import fake_only

DATE, TIME = r"^\d{4}-\d{2}-\d{2}$", r"^([01]\d|2[0-3]):[0-5]\d$"


class ParseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str  # the library checks it (422 text_required / text_too_long), so the codes are its own
    today: date | None = None
    time_zone: str | None = None
    rich: bool = False  # opt in to location, notes, duration_minutes and attendees; false keeps the answer as it was


class EventBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=200)
    start_date: str = Field(pattern=DATE)
    start_time: str | None = Field(default=None, pattern=TIME)
    all_day: bool = False
    end_date: str | None = Field(default=None, pattern=DATE)
    end_time: str | None = Field(default=None, pattern=TIME)


def register(app: FastAPI) -> None:
    @app.post("/tasks/parse")
    def parse(body: ParseBody, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        state = request.app.state
        with unit(request) as session:
            zone = viewer_zone(request, session, user_id, body.time_zone)
            end_of_day = prefs_of(request, session, user_id).end_of_day
        day = body.today or tasks.viewer_today(clock_now(request), zone)
        try:
            result = parse_capture(body.text, user_id=user_id, today=day, time_zone=zone, end_of_day=end_of_day,
                                   llm=state.capture_llm, resolver=state.contacts, guard=state.capture_guard,
                                   rich=body.rich)
        except CaptureError as exc:
            raise ApiError(exc.code, exc.message, status=exc.status) from None
        return result.to_dict()

    @app.get("/tasks/links/search")
    def search_links(request: Request, kind: str = "contact", q: str = Query("", max_length=100),
                     limit: int = Query(10, ge=1, le=25), user_id: str = Depends(current_user_id)) -> dict:
        with unit(request) as session:
            return {"items": request.app.state.contacts.search(session, user_id, kind, q, limit)}

    @app.post("/capture/events", status_code=201)
    def accept_event(body: EventBody, request: Request, user_id: str = Depends(current_user_id)) -> dict:
        fake_only(request)
        return request.app.state.accepted_events.add(user_id, body.model_dump())

    @app.get("/capture/events")
    def accepted_events(request: Request, user_id: str = Depends(current_user_id)) -> dict:
        fake_only(request)
        return {"items": [e for e in request.app.state.accepted_events.items if e["user_id"] == user_id]}
