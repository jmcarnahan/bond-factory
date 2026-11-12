"""Sync: the upload route for the synced tables (notes, tasks, notices, push_devices), the sync token and the JWKS.

    POST /sync/upload      a device's queued writes, one verdict per op (session required)
    POST /sync/token       an ES256 token the sync service accepts (503 sync_off when SDK_EXAMPLE_SYNC_URL is empty)
    GET  /sync/jwks.json   the public key set (404 when sync is off; cacheable)

Fake mode defaults SDK_EXAMPLE_SYNC_URL to a stand-in endpoint, so the token route mints out of the box; setting it to an
empty value turns sync off. Real mode has sync off until the URL is set.

bond_sync_py raises its own exceptions and returns verdicts; this module is where they become ApiError.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from bond_service_kit import ApiError
from bond_sync_py import (
    Ctx,
    DbUnavailable,
    Host,
    Rejected,
    Route,
    Skipped,
    SyncKeyError,
    SyncTokenSettings,
    UploadRequest,
    is_configured,
    jwks,
    mint_sync_token,
    server_now_iso,
    upload,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .. import sync_todo, tasks_wiring
from ..auth_dep import current_user_id
from ..models.notices import Notice
from ..models.push import PushDevice
from ..models.sync import Note
from ..models.tasks import Task

KEY_FILE = "sync_key.pem"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# --- the host: what the dispatcher needs from this app --------------------------------------------------------------


def _title(data: dict) -> str:
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise Rejected("title_required")  # code stays "invalid"
    return title


def _own_live_note(session, ctx: Ctx, note_id: str) -> Note | None:
    note = session.get(Note, note_id)
    if note is None or note.owner_user_id != ctx.user or note.deleted_at is not None:
        return None
    return note


def _notes(session, ctx: Ctx, op, data: dict) -> None:
    """put, patch and delete for notes. The owner is always the session user; someone else's row looks missing."""
    if op.op == "put":
        session.add(Note(id=op.id, owner_user_id=ctx.user, title=_title(data), body=data.get("body"), updated_at=_now()))
        session.flush()  # a clash with an existing id surfaces here as IntegrityError
        return
    note = _own_live_note(session, ctx, op.id)
    if op.op == "delete":
        if note is None:
            raise Skipped()  # nothing to delete: the effect already exists
        note.deleted_at = note.updated_at = _now()
        return
    if note is None:
        raise Rejected("Not found", code="not_found")
    if "title" in data:
        note.title = _title(data)
    if "body" in data:
        note.body = data["body"]
    note.updated_at = _now()


def build_host(app: FastAPI) -> Host:
    """Four synced tables: ``notes`` (handled here), ``tasks``, ``notices`` and ``push_devices`` (routes shipped by
    the libs, wired in ``sync_todo.py``)."""
    tasks_wiring.install(app)  # the preferences, link hook and sender the TODO routes use (routes load alphabetically)
    routes = {("notes", None): Route(frozenset({"put", "patch", "delete"}), _notes, ("title", "body"))}
    routes.update({key: Route(r.ops, r.handler, r.reads) for key, r in sync_todo.todo_routes(app).items()})
    return Host(
        routes=routes,
        tables={"notes": Note.__table__, "tasks": Task.__table__, "notices": Notice.__table__,
                "push_devices": PushDevice.__table__},
        single_action=frozenset({"notes", "tasks", "notices", "push_devices"}),
        reject_for=sync_todo.reject_for,
        already_written=sync_todo.already_written,
    )


# --- token settings ----------------------------------------------------------------------------------------------


def _generate_key(path: Path) -> None:
    """Fake mode only: a throwaway signing key, created once. Never used outside a local run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)


def token_settings(request: Request) -> SyncTokenSettings | None:
    """The sync token settings, or None when sync is off. BOND_SYNC_* names supply key, kid and lifetime; the endpoint
    is SDK_EXAMPLE_SYNC_URL. In fake mode a missing key is generated into out/sync_key.pem on first use."""
    app_settings = request.app.state.settings
    if not app_settings.sync_url:
        return None
    cfg = replace(SyncTokenSettings.from_env(), url=app_settings.sync_url)
    if not (cfg.private_key or cfg.private_key_file) and app_settings.mode == "fake":
        path = Path(request.app.state.out_dir) / KEY_FILE
        if not path.exists():
            _generate_key(path)
        cfg = replace(cfg, private_key_file=str(path))
    return cfg if is_configured(cfg) else None


def _sync_off() -> ApiError:
    return ApiError("sync_off", "Sync is not set up on this server.", status=503)


def register(app: FastAPI) -> None:
    router = APIRouter(prefix="/sync", tags=["sync"])
    host = build_host(app)

    @router.post("/upload")
    def upload_route(body: UploadRequest, request: Request, background: BackgroundTasks,
                     user_id: str = Depends(current_user_id)):
        """Always 200 with one verdict per op; only an unavailable database answers 503 so the client retries."""
        try:
            return upload(request.app.state.session_factory, host, Ctx(user=user_id, background=background), body).wire()
        except DbUnavailable:
            error = ApiError("db_unavailable", "The database is not answering. Try again in a few seconds", status=503)
            return JSONResponse({"detail": error.detail()}, status_code=503, headers={"Retry-After": "5"})

    @router.post("/token")
    def token_route(request: Request, user_id: str = Depends(current_user_id)) -> dict:
        cfg = token_settings(request)
        if cfg is None:
            raise _sync_off()
        try:
            token, expires = mint_sync_token(cfg, user_id)
        except SyncKeyError:
            raise _sync_off() from None
        return {
            "token": token,
            "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endpoint": cfg.url,
            "server_now": server_now_iso(),
        }

    @router.get("/jwks.json")
    def jwks_route(request: Request) -> JSONResponse:
        cfg = token_settings(request)
        if cfg is None:
            raise ApiError("not_found", "Not found.", status=404)
        return JSONResponse(jwks(cfg), headers={"Cache-Control": "public, max-age=300"})

    app.include_router(router)
