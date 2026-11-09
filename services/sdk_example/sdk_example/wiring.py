"""App-level objects: auth settings, storage, jobs registry, clock, middleware, fake-mode bootstrap.

`install(app)` runs once from `routes/a0_wiring.py` (main.py is not edited). Everything is kept on `app.state`:
`auth_settings`, `storage`, `job_registry`, `clock`, `limiters`, `out_dir`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from bond_auth_py import AuthSettings, assert_startup_safe, default_mock
from bond_jobs import HandlerRegistry
from bond_service_kit import (
    Clock,
    RateLimiter,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
    UploadLimit,
    install_error_handlers,
)
from bond_storage import LocalStorageService
from fastapi import FastAPI, Request
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from starlette.middleware import Middleware

from .db import Base, session_scope
from .models.auth import MOCK_IDENTITIES, ensure_demo_users
from .models.jobs import BackgroundJob
from .settings import Settings, out_dir_for

log = logging.getLogger("sdk_example")
APP_NAME = "sdk_example"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MOCK_FILE = "mock_identities.json"


def build_auth_settings(settings: Settings, mock_file: Path | None) -> AuthSettings:
    """Fake mode: mock verifier (not tied to pytest) and demo sign-in. Real mode: Firebase from the environment."""
    fake = settings.mode == "fake"
    return AuthSettings.from_env(
        jwt_secret=settings.auth_secret, issuer=APP_NAME, audience=APP_NAME, access_ttl_minutes=10080,
        app_name=APP_NAME, tier="mock" if fake else "firebase", mock_enabled_only_under_test=not fake,
        mock_identities_file=str(mock_file) if fake and mock_file else None, demo_enabled=fake,
    )


def write_mock_identities(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(MOCK_IDENTITIES), indent=2) + "\n")
    return path


def bootstrap_schema(engine: Engine) -> None:
    """Fake mode only. An EMPTY database gets the tables and is stamped at the migration head, so a later
    `alembic upgrade head` is a no-op instead of a clash. A migrated database is left alone. A database that has
    tables but no migration record is stale: it is not touched (stamping it would bless a schema nobody checked)
    and a warning says to run `make migrate`."""
    existing = set(inspect(engine).get_table_names())
    if "alembic_version" in existing:
        return
    if existing:
        log.warning("The database has tables but no migration record; not touching it. "
                    "Run `make migrate` (or delete the file) before starting.")
        return
    Base.metadata.create_all(engine)
    scripts = Path(__file__).resolve().parents[1] / "alembic"
    if not scripts.is_dir():
        return
    config = Config()  # no ini: only the script directory is read, env.py never runs
    config.set_main_option("script_location", str(scripts))
    head = ScriptDirectory.from_config(config).get_current_head()
    if head:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": head})


def client_ip(request: Request) -> str:
    """The last hop of X-Forwarded-For (the one the nearest proxy appended; earlier hops are client-controlled),
    else the socket peer."""
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    hop = forwarded.split(",")[-1].strip() if forwarded else ""
    if hop:
        return hop[:45]
    return (request.client.host if request.client else "unknown")[:45]


def set_now(app: FastAPI, at: datetime | None) -> None:
    """Pin the scheduling clock (fake mode demos), or None to run on real time again. Lock stamps and rate
    limits always read the real clock."""
    clock: Clock = app.state.clock
    clock.unfreeze() if at is None else clock.freeze(at)


def install(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    fake = settings.mode == "fake"
    out = out_dir_for(settings.database_url)
    mock_file = write_mock_identities(out / MOCK_FILE) if fake else None
    auth = build_auth_settings(settings, mock_file)
    assert_startup_safe(auth)
    if mock_file is not None:
        default_mock().load_file(str(mock_file))
        bootstrap_schema(app.state.engine)
        if inspect(app.state.engine).has_table("users"):
            with session_scope(app.state.session_factory) as session:
                ensure_demo_users(session)
    app.state.out_dir = out
    app.state.auth_settings = auth
    app.state.storage = LocalStorageService(out / "uploads")
    app.state.job_registry = HandlerRegistry(BackgroundJob)
    app.state.clock = Clock()
    app.state.limiters = {"auth": RateLimiter("20/minute"), "download_token": RateLimiter("30/minute"),
                          "download_ip": RateLimiter("120/minute")}
    install_error_handlers(app)
    app.add_middleware(SecurityHeadersMiddleware)
    # Appended, so they sit inside CORS (which main.py added first): a 413 or a 500 still carries the CORS
    # headers, and a browser reads the answer instead of reporting a network error.
    app.user_middleware.append(Middleware(UploadLimit, max_bytes=MAX_UPLOAD_BYTES, paths=("/documents",)))
    app.user_middleware.append(Middleware(UnhandledErrorMiddleware))
