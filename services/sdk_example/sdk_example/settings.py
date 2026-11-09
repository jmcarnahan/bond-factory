"""Settings read from the environment. Fake mode needs no variables at all."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

OUT_DIR = Path("out")
DEV_SECRET = "dev-secret-change-me"


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _oauth_key(mode: str) -> str:
    """BOND_OAUTH_KEY, or in fake mode a key generated once and kept in out/oauth.key."""
    env = os.environ.get("BOND_OAUTH_KEY")
    if env:
        return env
    if mode != "fake":
        return ""
    path = OUT_DIR / "oauth.key"
    if path.exists():
        return path.read_text().strip()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
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
        return cls(
            mode=mode,
            database_url=env("SDK_EXAMPLE_DATABASE_URL", "sqlite:///out/sdk_example.db"),
            auth_secret=auth_secret,
            cors_origins=cors_origins,
            redirect_allowlist=_split(env("SDK_EXAMPLE_REDIRECT_ALLOWLIST", "http://localhost:8078")),
            oauth_key=_oauth_key(mode),
            tz=env("SDK_EXAMPLE_TZ", "UTC"),
        )
