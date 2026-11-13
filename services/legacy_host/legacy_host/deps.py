"""Request helpers: the caller (header `X-User`) and the app clock."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import Body, HTTPException, Request

#: a JSON object body; a missing body is an empty object, and keys the route does not know stay in it
JsonBody = Annotated[dict[str, Any], Body(default_factory=dict)]


def current_user(request: Request) -> str:
    user_id = (request.headers.get("X-User") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": "unauthorized", "message": "Sign in first."})
    return user_id


def clock_now(request: Request) -> datetime:
    """The app clock as naive UTC (freezable: `app.state.clock.freeze(...)`)."""
    return request.app.state.clock.utcnow_naive()
