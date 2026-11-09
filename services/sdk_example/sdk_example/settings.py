"""Settings read from the environment. Fake mode needs no variables at all."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

OUT_DIR = Path("out")
DEV_SECRET = "dev-secret-change-me-dev-secret-change-me"  # >= 32 bytes so PyJWT does not warn; never use in real mode


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def out_dir_for(database_url: str) -> Path:
    """Where generated files live: next to a SQLite database file (a test's temp dir), else out/.
    One rule for every generated file (oauth key, mock identities, sync key, uploads)."""
    if database_url.startswith("sqlite"):
        path = database_url.split("///", 1)[-1]
        if path and path != ":memory:":
            return Path(path).resolve().parent
    return OUT_DIR


def _oauth_key(mode: str, out_dir: Path) -> str:
    """BOND_OAUTH_KEY, or in fake mode a key generated once and kept in oauth.key next to the database."""
    env = os.environ.get("BOND_OAUTH_KEY")
    if env:
        return env
    if mode != "fake":
        return ""
    path = out_dir / "oauth.key"
    if path.exists():
        return path.read_text().strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(32)
    path.write_text(key)
    return key


@dataclass(frozen=True)
class Settings:
    mode: str = "fake"
    database_url: str = "sqlite:///out/sdk_example.db"
    auth_secret: str = DEV_SECRET
    cors_origins: tuple[str, ...] = ("http://localhost:8078",)
    redirect_allowlist: tuple[str, ...] = ("http://localhost:8078",)
    oauth_key: str = ""
    tz: str = "UTC"
    sync_url: str = ""  # PowerSync endpoint handed to clients by POST /sync/token; empty = sync off

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get
        mode = env("SDK_EXAMPLE_MODE", "fake")
        auth_secret = env("SDK_EXAMPLE_AUTH_SECRET", DEV_SECRET)
        if mode != "fake" and auth_secret == DEV_SECRET:
            raise RuntimeError("SDK_EXAMPLE_AUTH_SECRET must be set in real mode")
        cors_origins = _split(env("SDK_EXAMPLE_CORS_ORIGINS", "http://localhost:8078"))
        if "*" in cors_origins:
            raise RuntimeError("SDK_EXAMPLE_CORS_ORIGINS must not contain '*' (credentials are on)")
        database_url = env("SDK_EXAMPLE_DATABASE_URL", "sqlite:///out/sdk_example.db")
        return cls(
            mode=mode,
            database_url=database_url,
            auth_secret=auth_secret,
            cors_origins=cors_origins,
            redirect_allowlist=_split(env("SDK_EXAMPLE_REDIRECT_ALLOWLIST", "http://localhost:8078")),
            oauth_key=_oauth_key(mode, out_dir_for(database_url)),
            tz=env("SDK_EXAMPLE_TZ", "UTC"),
            sync_url=env("SDK_EXAMPLE_SYNC_URL", ""),
        )
