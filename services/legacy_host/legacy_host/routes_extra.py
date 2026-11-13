"""Routes over the tables that pre-date the modules: preferences (`user_prefs`) and share links (`file_share_grants`).

    GET/PUT /prefs         over `bond_tasks_py.usersettings`, plus the app's own `theme`
    POST /shares           mint a link (needs a caller)        GET /shares/{token}   resolve and claim (no caller)
"""

from __future__ import annotations

from typing import Any

import bond_tasks_py as tasks
from bond_storage import GrantUnavailable, claim, mint, resolve
from bond_tasks_py import SettingsUpdate, TaskError
from fastapi import APIRouter, Depends, Request

from .db import session_scope
from .deps import JsonBody, clock_now, current_user
from .models import Attachment, ShareGrant, Task, UserPrefs
from .routes import WORK_DAY
from .wire import naive_iso

router = APIRouter()


def _prefs_answer(session: Any, user_id: str, warnings: list[str] | tuple = ()) -> dict:
    row = session.get(UserPrefs, user_id)
    prefs = tasks.get_settings(session, UserPrefs, user_id, WORK_DAY)
    answer = tasks.settings_item(prefs, warnings, tasks.settings_overridden(row))
    answer["theme"] = row.theme if row is not None else None
    return answer


@router.get("/prefs")
def get_prefs(request: Request, user_id: str = Depends(current_user)) -> dict:
    with session_scope(request.app.state.session_factory) as session:
        return _prefs_answer(session, user_id)


@router.put("/prefs")
def put_prefs(request: Request, body: JsonBody,
              user_id: str = Depends(current_user)) -> dict:
    """The work-day fields go through `update_settings`; `theme` is the app's own column. Unknown keys are ignored."""
    sent = {k: v for k, v in body.items() if k in SettingsUpdate.model_fields}
    with session_scope(request.app.state.session_factory) as session:
        try:
            data = SettingsUpdate(**sent)
        except ValueError as exc:
            raise TaskError("invalid_request", str(exc).splitlines()[0], 422) from None
        _, warnings = tasks.update_settings(session, settings_model=UserPrefs, task_model=Task, user_id=user_id,
                                            data=data, tz="UTC", now=clock_now(request), defaults=WORK_DAY)
        if "theme" in body:
            session.get(UserPrefs, user_id).theme = body["theme"]
        return _prefs_answer(session, user_id, warnings)


def _document(session: Any, document_id: str) -> Attachment | None:
    return session.get(Attachment, document_id)


@router.post("/shares", status_code=201)
def create_share(request: Request, body: JsonBody,
                 user_id: str = Depends(current_user)) -> dict:
    with session_scope(request.app.state.session_factory) as session:
        document = _document(session, str(body.get("attachment_id") or ""))
        if document is None:
            raise TaskError("attachment_not_found", "Attachment not found.", 404)
        extra = {"recipient_note": body["recipient_note"]} if "recipient_note" in body else None
        grant, raw = mint(session, document, grant_model=ShareGrant, user_id=user_id, extra=extra,
                          max_downloads=body.get("max_downloads", 20), ttl_days=body.get("ttl_days", 30),
                          now=request.app.state.clock.utcnow_naive)
        return {"id": grant.id, "token": raw, "expires_at": naive_iso(grant.expires_at)}


@router.get("/shares/{token}")
def open_share(token: str, request: Request) -> dict:
    """The recipient is not a user: the token is the credential. Resolves and claims one download."""
    clock = request.app.state.clock.utcnow_naive
    with session_scope(request.app.state.session_factory) as session:
        grant, document = resolve(session, token, grant_model=ShareGrant, document_loader=_document, now=clock)
        ip = request.client.host if request.client else None
        if not claim(session, grant, ip, now=clock):
            raise GrantUnavailable
        return {"attachment_id": document.id, "filename": document.filename, "downloads": grant.download_count,
                "recipient_note": grant.recipient_note}
