"""Per-call runtime settings for library use: keys and directories as arguments, not environment variables.

WHY a Runtime is authoritative: the isolated child inherits the parent's environment, so a caller that passes
``anthropic_api_key=None`` must get "no key", never a paid key that happens to sit in the environment. When no
Runtime is set (the service, the CLI, the tests) every reader falls back to the environment exactly as before.
A ContextVar is used so concurrent threads each see their own Runtime; a plain ``Thread`` does not inherit it
(run it under ``contextvars.copy_context().run``), a child interpreter starts empty and sets it first.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

SOLAR_KEY_ENV = ("GOOGLE_SOLAR_API_KEY",)  # only this key enables billable Solar calls


@dataclass(frozen=True)
class Runtime:
    cache_dir: Path
    anthropic_api_key: str | None = None
    google_solar_api_key: str | None = None
    overpass_urls: tuple[str, ...] | None = None
    footprint_stage_s: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cache_dir, Path):
            object.__setattr__(self, "cache_dir", Path(self.cache_dir))


_current: ContextVar[Runtime | None] = ContextVar("roof_measure_runtime", default=None)


def current() -> Runtime | None:
    return _current.get()


@contextmanager
def use(runtime: Runtime) -> Iterator[None]:
    token = _current.set(runtime)
    try:
        yield
    finally:
        _current.reset(token)


def anthropic_key() -> str | None:
    rt = _current.get()
    return rt.anthropic_api_key if rt else os.environ.get("ANTHROPIC_API_KEY")


def solar_key() -> str | None:
    rt = _current.get()
    if rt:
        return rt.google_solar_api_key
    for name in SOLAR_KEY_ENV:
        if os.environ.get(name):
            return os.environ[name]
    return None


def cache_root() -> Path | None:
    rt = _current.get()
    return rt.cache_dir if rt else None


def overpass_urls() -> tuple[str, ...] | None:
    """The Runtime's mirrors (None: the built-in defaults); None without a Runtime, so the caller reads the env."""
    rt = _current.get()
    return rt.overpass_urls if rt else None


def footprint_stage_s() -> float | None:
    """The Runtime's footprint stage cap (60 s when unset); None without a Runtime, so the caller reads the env."""
    rt = _current.get()
    return (rt.footprint_stage_s or 60.0) if rt else None
