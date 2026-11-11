"""Environment-driven settings (plan section 3.5), read once per app."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
IMAGE_FIXTURES_DIR = Path("/app/fixtures")


def resolve_fixtures_dir(env: dict[str, str] | None = None) -> Path:
    """``ROOF_MEASURE_FIXTURES``, else the repo ``fixtures/`` next to the source tree, else ``/app/fixtures``.

    A non-editable install (the Docker image) has no source tree beside the package, so the image sets the env var.
    """
    env = os.environ if env is None else env
    if env.get("ROOF_MEASURE_FIXTURES"):
        return Path(env["ROOF_MEASURE_FIXTURES"])
    repo = SERVICE_DIR.parents[1] / "fixtures"
    return repo if repo.is_dir() else IMAGE_FIXTURES_DIR


FIXTURES_DIR = resolve_fixtures_dir()
DEFAULT_CORS = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"


def _int(env: dict[str, str], name: str, default: int) -> int:
    try:
        return int(env.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    workers: int = 2
    queue_max: int = 10
    retention_days: float = 14.0
    job_timeout_s: float = 180.0
    debug: bool = False
    cors_regex: str = DEFAULT_CORS
    fixtures_dir: Path = field(default_factory=resolve_fixtures_dir)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ) if env is None else env
        return cls(data_dir=Path(env.get("DATA_DIR") or SERVICE_DIR / "data"),
                   workers=_int(env, "ROOF_MEASURE_WORKERS", 2), queue_max=_int(env, "ROOF_MEASURE_QUEUE_MAX", 10),
                   retention_days=float(_int(env, "ROOF_MEASURE_JOB_RETENTION_DAYS", 14)),
                   job_timeout_s=float(_int(env, "ROOF_MEASURE_JOB_TIMEOUT_S", 180)),
                   debug=env.get("ROOF_MEASURE_DEBUG") == "1",
                   cors_regex=env.get("ROOF_MEASURE_CORS_ORIGIN_REGEX") or DEFAULT_CORS,
                   fixtures_dir=resolve_fixtures_dir(env))


def keys_present(env: dict[str, str] | None = None) -> tuple[bool, bool]:
    """(Solar key present, Anthropic key present): both change the output, so both enter the cache key."""
    env = os.environ if env is None else env
    solar = bool(env.get("GOOGLE_SOLAR_API_KEY"))
    return solar, bool(env.get("ANTHROPIC_API_KEY"))
