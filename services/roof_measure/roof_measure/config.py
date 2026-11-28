"""Per-call runtime settings for library use: directories and mirrors as arguments, not environment variables.

A Runtime carries the cache directory and the Overpass mirrors of one call, so a caller's arguments win over the
process environment. When no Runtime is set (the tests) every reader falls back to the environment.
A ContextVar is used so concurrent threads each see their own Runtime; a plain ``Thread`` does not inherit it
(run it under ``contextvars.copy_context().run``), a child interpreter starts empty and sets it first.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Runtime:
    cache_dir: Path
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
