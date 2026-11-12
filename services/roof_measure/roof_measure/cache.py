"""Tiny on-disk cache for every network fetch.

WHY: the POC re-runs the same sample address constantly; caching raw responses makes those
runs offline and fast, and gives tests one seam (`_send`) to replace the network.
Entries are keyed by a sha256 of the request and carry a max age. `stats` counts real
network requests so a run can prove it made none.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from . import config
from .deadline import Deadline

log = logging.getLogger(__name__)

DAY = 86400.0
USER_AGENT = "roof-measure-poc/0.1 (research prototype)"
_session = requests.Session()
# What a failed or malformed network fetch can raise; callers catch exactly this.
NET_ERRORS = (requests.RequestException, ValueError, KeyError)


@dataclass
class Stats:
    """Counters for one process: real requests made and bytes pulled."""

    requests: int = 0
    bytes: int = 0
    hits: int = 0


stats = Stats()


def cache_dir() -> Path:
    """Cache root: $ROOF_MEASURE_CACHE or `services/roof_measure/cache/` (gitignored)."""
    root = config.cache_root()
    if root:
        d = root
    else:
        env = os.environ.get("ROOF_MEASURE_CACHE")
        d = Path(env) if env else Path(__file__).resolve().parents[1] / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _send(method: str, url: str, params: dict | None, data: dict | None,
          headers: dict | None, timeout: float) -> bytes:
    """The single network seam. Tests replace this function."""
    h = {"User-Agent": USER_AGENT, **(headers or {})}
    r = _session.request(method, url, params=params, data=data, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.content


def _key(method: str, url: str, params: dict | None, data: dict | None) -> str:
    blob = json.dumps([method, url, params or {}, data or {}], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


_FORCE: contextvars.ContextVar[bool] = contextvars.ContextVar("roof_measure_force_refresh", default=False)


_DEADLINE: contextvars.ContextVar[Deadline | None] = contextvars.ContextVar("roof_measure_deadline", default=None)


@contextlib.contextmanager
def deadline_scope(deadline: Deadline | None) -> Iterator[None]:
    """Every fetch in this context (and in threads started with a copied context) honours ``deadline``."""
    token = _DEADLINE.set(deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def describe_error(exc: BaseException) -> str:
    """A short, URL-free description of a fetch failure (request errors embed the URL, address included)."""
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    return f"HTTP {status}" if status else type(exc).__name__


def host_of(url: str) -> str:
    return url.split("/")[2] if "//" in url else url


def purge_old(days: float = 30.0, now: float | None = None) -> int:
    """Delete cached bodies (and stray temp files) not written for ``days`` days; returns how many."""
    cutoff = (time.time() if now is None else now) - days * 86400
    n = 0
    for f in list(cache_dir().glob("*.bin")) + list(cache_dir().glob("*.tmp")):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        except OSError:
            continue
    return n


def force_refresh(flag: bool = True) -> None:
    """For the current thread/context only: skip reading cached bodies (fresh ones are still written)."""
    _FORCE.set(flag)


@contextlib.contextmanager
def force_scope(flag: bool) -> Iterator[None]:
    """Set the force flag for this block and restore the caller's value afterwards (never clobber it)."""
    token = _FORCE.set(flag)
    try:
        yield
    finally:
        _FORCE.reset(token)


class BadResponse(ValueError):
    """A 200 response whose body is an error, a timeout remark or not the expected format."""


Validator = Callable[[bytes], None]


def json_validator(check: Callable[[Any], None] | None = None) -> Validator:
    """Validator: body parses as JSON and (optionally) `check(obj)` raises BadResponse/ValueError if not."""

    def v(body: bytes) -> None:
        try:
            obj = json.loads(body)
        except ValueError as e:
            raise BadResponse(f"response is not JSON: {e}") from e
        if check:
            check(obj)

    return v


def evict(url: str, *, method: str = "GET", params: dict | None = None, data: dict | None = None) -> None:
    """Delete one cached entry (used when a cached body turns out to be corrupt)."""
    (cache_dir() / (_key(method, url, params, data) + ".bin")).unlink(missing_ok=True)


def fetch_bytes(url: str, *, method: str = "GET", params: dict | None = None, data: dict | None = None,
                headers: dict | None = None, max_age_s: float = 30 * DAY, timeout: float = 60.0,
                retries: int = 2, validate: Validator | None = None, deadline: Deadline | None = None) -> bytes:
    """Return the response body, from disk when fresh, else from the network (then stored).

    WHY `validate`: services answer HTTP 200 with an error object or a timeout remark. A body is
    written to disk only after `validate(body)` passes, and a cached body that no longer passes
    (an entry poisoned by an older version) is discarded and refetched.

    With a ``deadline`` (argument, else the ambient ``deadline_scope``) each attempt's timeout is capped by the time
    left, at most one retry is made, no retry sleeps past the deadline, and ``DeadlineExceeded`` is raised when it
    has passed.
    """
    deadline = deadline or _DEADLINE.get()
    if deadline is not None:
        retries = min(retries, 1)
    path = cache_dir() / (_key(method, url, params, data) + ".bin")
    if not _FORCE.get() and path.exists() and (time.time() - path.stat().st_mtime) < max_age_s:
        body = path.read_bytes()
        try:
            if validate:
                validate(body)
            stats.hits += 1
            return body
        except ValueError:
            log.warning("discarding invalid cache entry for %s", host_of(url))
    last: Exception | None = None
    for attempt in range(retries + 1):
        if deadline is not None:
            deadline.check("fetch")
        try:
            body = _send(method, url, params, data, headers, deadline.timeout(timeout) if deadline else timeout)
            if validate:
                validate(body)
            break
        except (requests.RequestException, BadResponse) as e:
            last = e
            log.warning("fetch from %s failed (%s), attempt %d", host_of(url), describe_error(e), attempt + 1)
            if attempt >= retries or (deadline is not None and deadline.remaining() < 1.5 * (attempt + 1)):
                raise
            time.sleep(1.5 * (attempt + 1))
    else:  # pragma: no cover  (the last attempt re-raises above)
        raise last  # type: ignore[misc]
    stats.requests += 1
    stats.bytes += len(body)
    # unique temp name in the same directory: concurrent writers of one key cannot clobber each other
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp.write(body)
    os.replace(tmp.name, path)
    return body


def fetch_json(url: str, *, check: Callable[[Any], None] | None = None, **kw: Any) -> Any:
    """`fetch_bytes` with JSON validation (plus an optional `check(obj)`), then parse."""
    return json.loads(fetch_bytes(url, validate=json_validator(check), **kw))
