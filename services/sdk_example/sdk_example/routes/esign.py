"""E-signing, the app's side: the fake-mode demo, the staff evidence export, the library's static assets.

    POST /esign/demo                       FAKE MODE ONLY (404 otherwise). A generated two-page sample PDF, one signer.
        body (all optional): {"expires_in_seconds": int (negative = already expired), "allow_typed": bool,
                              "allow_drawn": bool, "signer_name": str}
        -> {"request_id", "sign_url": "/esign/sign/<token>"}
    POST /esign/demo/{request_id}/void     FAKE MODE ONLY: void a demo request (so the walk can open a voided page)
    GET  /esign/requests/{id}/evidence     staff only (the capability below): the evidence export as JSON
    GET  /esign/static/{name}              the library's panel assets (only `asset_names()`)

The public signing pages are in `esign_pages.py`. A real app replaces the demo route with one that creates a request
for its own document and sends the link by mail.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from bond_esign import (
    AnchorRule,
    EsignError,
    Policy,
    SignerSpec,
    asset_names,
    asset_path,
    create_request,
    evidence,
    issue_token,
    void,
)
from bond_service_kit import ApiError
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from ..auth_dep import require_capability
from ..db import session_scope
from ..esign_sample import ANCHOR_TEXT, sample_pdf
from ..esign_wiring import CONSENT, TABLES, install, store_original

#: Who may read the evidence export. The example reuses a seeded capability; a real app names its own staff rule.
EVIDENCE_CAPABILITY = "tasks.read_all"
MEDIA = {".css": "text/css", ".js": "text/javascript", "": "text/plain"}


class DemoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_seconds: int | None = None
    allow_typed: bool = True
    allow_drawn: bool = True
    signer_name: str = "Pat Sample"


def fake_only(request: Request) -> None:
    if request.app.state.settings.mode != "fake":
        raise ApiError("not_found", "Not found.", status=404)


def register(app: FastAPI) -> None:
    install(app)
    router = APIRouter(tags=["esign"])

    @router.post("/esign/demo")
    def demo(request: Request, body: DemoBody | None = None) -> dict:
        fake_only(request)
        body = body or DemoBody()
        now = request.app.state.clock.utcnow_naive()
        pdf = sample_pdf()
        spec = SignerSpec(name=body.signer_name, email="pat@example.com", anchor=AnchorRule(ANCHOR_TEXT))
        policy = Policy(allow_typed=body.allow_typed, allow_drawn=body.allow_drawn)
        with session_scope(request.app.state.session_factory) as session:
            try:
                row = create_request(session, TABLES, pdf=pdf, title="Sample Service Agreement", signers=[spec],
                                     consent=CONSENT, now=now, policy=policy, subject_type="demo",
                                     subject_id=str(uuid.uuid4()))
            except ValueError as exc:
                raise ApiError("invalid_demo", str(exc), status=422) from None
            store_original(request.app, row.id, pdf)
            signer = session.query(TABLES.signer).filter_by(request_id=row.id).one()
            token = issue_token(session, TABLES, signer, now=now)
            if body.expires_in_seconds is not None:
                # A demo knob: the library refuses a past expiry at creation, so the walk's already-expired
                # request is made by moving the date afterwards. A real app never edits the row.
                row.expires_at = now + timedelta(seconds=body.expires_in_seconds)
            return {"request_id": row.id, "sign_url": f"/esign/sign/{token}"}

    @router.post("/esign/demo/{request_id}/void")
    def demo_void(request_id: str, request: Request) -> dict:
        fake_only(request)
        now = request.app.state.clock.utcnow_naive()
        with session_scope(request.app.state.session_factory) as session:
            row = session.get(TABLES.request, request_id)
            if row is None:
                raise ApiError("not_found", "No such request.", status=404)
            try:
                void(session, TABLES, row, reason="voided by the demo", ctx=None, now=now)
            except EsignError as exc:
                raise ApiError(exc.code, exc.message, status=409) from None
            return {"request_id": row.id, "status": row.status}

    @router.get("/esign/requests/{request_id}/evidence")
    def evidence_export(request_id: str, request: Request,
                        user_id: Annotated[str, Depends(require_capability(EVIDENCE_CAPABILITY))]) -> dict:
        with session_scope(request.app.state.session_factory) as session:
            row = session.get(TABLES.request, request_id)
            if row is None:
                raise ApiError("not_found", "No such request.", status=404)
            return evidence(session, TABLES, row)

    @router.get("/esign/static/{name}")
    def static(name: str) -> FileResponse:
        if name not in asset_names():
            raise ApiError("not_found", "Not found.", status=404)
        suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
        return FileResponse(asset_path(name), media_type=MEDIA.get(suffix, "text/plain"),
                            headers={"Cache-Control": "public, max-age=3600"})

    app.include_router(router)
