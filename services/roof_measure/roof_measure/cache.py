"""Tiny on-disk cache for every network fetch.

WHY: the POC re-runs the same sample address constantly; caching raw responses makes those
runs offline and fast, and gives tests one seam (`_send`) to replace the network.
Entries are keyed by a sha256 of the request and carry a max age. `stats` counts real
network requests so a run can prove it made none.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

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
                retries: int = 2, validate: Validator | None = None) -> bytes:
    """Return the response body, from disk when fresh, else from the network (then stored).

    WHY `validate`: services answer HTTP 200 with an error object or a timeout remark. A body is
    written to disk only after `validate(body)` passes, and a cached body that no longer passes
    (an entry poisoned by an older version) is discarded and refetched.
    """
    path = cache_dir() / (_key(method, url, params, data) + ".bin")
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_s:
        body = path.read_bytes()
        try:
            if validate:
                validate(body)
            stats.hits += 1
            return body
        except ValueError:
            log.warning("discarding invalid cache entry for %s", url)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            body = _send(method, url, params, data, headers, timeout)
            if validate:
                validate(body)
            break
        except (requests.RequestException, BadResponse) as e:
            last = e
            log.warning("fetch %s failed (%s), attempt %d", url, e, attempt + 1)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    else:
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
