"""COPY AS IS (trim to what the app has). Session routes the example keeps under /auth: demo and me.

The library mounts the rest (`/auth/signin/*`, `/auth/refresh`, `/auth/logout`, `/auth/sessions/revoke-all`,
`/auth/providers`: see `signin_wiring.py`); break-glass is `break_glass.py`; fake-mode `simulate-reuse` is in
`fake_routes.py`. Every sign-in path ends in `session_answer`.
"""

from __future__ import annotations

import re
from typing import Annotated

from bond_auth_py import DEACTIVATED, AuthRefused
from bond_service_kit import ApiError
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth_dep import auth_settings, current_user, refusal
from ..break_glass import Delivery
from ..break_glass import register as register_break_glass
from ..db import session_scope
from ..models.auth import User, utcnow
from ..session_answer import require_cookie_origin, session_answer

LANGUAGE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
CurrentUser = Annotated[User, Depends(current_user)]


class DemoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=64)
    delivery: Delivery = None


class MeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str = Field(pattern=LANGUAGE.pattern)


def register(app: FastAPI) -> None:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/demo")
    def demo(body: DemoBody, request: Request, response: Response) -> dict:
        if not auth_settings(request).demo_enabled:
            raise ApiError("not_found", "Not found", status=404)
        require_cookie_origin(request, body.delivery)
        with session_scope(request.app.state.session_factory) as session:
            user = session.get(User, body.user_id)
            if user is None:
                raise ApiError("not_found", "No such demo user.", status=404)
            if not user.is_active:
                raise refusal(AuthRefused(DEACTIVATED))
            user.last_sign_in_at = utcnow()
            return session_answer(request, session, response, user, provider="demo", auth_time=None,
                                  delivery=body.delivery)

    @router.get("/me")
    def me(user: CurrentUser) -> dict:
        return {"user": user.public()}

    @router.patch("/me")
    def patch_me(body: MeBody, request: Request, user: CurrentUser) -> dict:
        with session_scope(request.app.state.session_factory) as session:
            row = session.get(User, user.id)
            row.language = body.language
            return {"user": row.public()}

    app.include_router(router)
    register_break_glass(app)
