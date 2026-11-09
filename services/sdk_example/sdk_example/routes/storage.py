"""Documents: upload, metadata, share links, and the public /d/<token> download."""

from __future__ import annotations

import os
import uuid
from typing import Annotated

from bond_service_kit import ApiError
from bond_storage import make_download_router, mint
from fastapi import APIRouter, Depends, FastAPI, File, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth_dep import current_user_id
from ..db import session_scope
from ..models.grants import Document, DownloadGrant
from ..wiring import MAX_UPLOAD_BYTES

SECONDS_MAX = 30 * 86400
UserId = Annotated[str, Depends(current_user_id)]


class ShareBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ttl_seconds: int = Field(default=7 * 86400, ge=1, le=SECONDS_MAX)
    max_downloads: int | None = Field(default=20, ge=1, le=1000)


def _clean_name(raw: str | None) -> str:
    name = os.path.basename((raw or "").replace("\\", "/")).strip().replace("\x00", "")
    return (name or "file")[:200]


def _kind(content_type: str | None) -> str:
    return "image" if (content_type or "").startswith("image/") else "file"


def _load_document(session: Session, document_id: str) -> Document | None:
    return session.get(Document, document_id)


def _owned(session: Session, document_id: str, user_id: str) -> Document:
    """The caller's own document; someone else's looks exactly like a missing one."""
    document = session.get(Document, document_id)
    if document is None or document.owner_user_id != user_id:
        raise ApiError("not_found", "No such document.", status=404)
    return document


def register(app: FastAPI) -> None:
    router = APIRouter(tags=["documents"])
    limiters = app.state.limiters

    @router.post("/documents", status_code=201)
    def upload(request: Request, file: Annotated[UploadFile, File()], user_id: UserId) -> dict:
        content = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise ApiError("too_large", "That file is too large.", status=413)
        if not content:
            raise ApiError("empty_file", "The file is empty.", status=400)
        document_id = str(uuid.uuid4())
        key = f"documents/{user_id}/{document_id}"
        content_type = (file.content_type or "application/octet-stream").split(";", 1)[0].strip()
        with session_scope(request.app.state.session_factory) as session:
            document = Document(id=document_id, storage_key=key, filename=_clean_name(file.filename),
                                content_type=content_type, kind=_kind(content_type), owner_user_id=user_id)
            session.add(document)
            session.flush()
            request.app.state.storage.upload_bytes(content, key, content_type=content_type)
            return document.public()

    @router.get("/documents/{document_id}")
    def meta(document_id: str, request: Request, user_id: UserId) -> dict:
        with session_scope(request.app.state.session_factory) as session:
            return _owned(session, document_id, user_id).public()

    @router.post("/documents/{document_id}/share")
    def share(document_id: str, request: Request, user_id: UserId, body: ShareBody | None = None) -> dict:
        body = body or ShareBody()
        with session_scope(request.app.state.session_factory) as session:
            document = _owned(session, document_id, user_id)
            grant, raw = mint(session, document, grant_model=DownloadGrant, user_id=user_id,
                              owner_type="document", owner_id=document.id, ttl_seconds=body.ttl_seconds,
                              max_downloads=body.max_downloads)
            return {"url": f"/d/{raw}", "expires_at": grant.expires_at.isoformat(timespec="seconds") + "Z"}

    def rate_limit(token_key: str, ip: str) -> bool:
        return limiters["download_token"].allow(token_key) and limiters["download_ip"].allow(ip)

    app.include_router(router)
    app.include_router(make_download_router(
        storage=app.state.storage, grant_model=DownloadGrant, document_loader=_load_document,
        session_factory=app.state.session_factory, rate_limit=rate_limit))
