"""Library facade: ``measure()`` returns the ``bond.roof_model/0.2`` envelope, ``MeasureError`` carries the job codes.

Imports only the standard library, ``errors`` and ``config`` at module level, so ``import roof_measure`` stays light.
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import config, errors

STAGES = ("geocode", "footprint", "lidar", "blocks", "model", "verify", "render")
KILL_GRACE_S = 30.0
METHODS = ("lidar_skeleton", "lidar_agent", "solar_agent", "auto")  # pipeline.METHODS + "auto"


class MeasureError(Exception):
    """A measurement that did not produce a roof: one of the job codes in ``errors.JOB_CODES``."""

    def __init__(self, code: str, message: str | None = None, retryable: bool | None = None) -> None:
        self.code = code
        self.message = message or errors.MESSAGES.get(code, errors.MESSAGES["measurement_failed"])
        self.retryable = errors.retryable_for(code) if retryable is None else retryable
        super().__init__(code, self.message, self.retryable)

    @classmethod
    def from_error(cls, err: dict[str, Any]) -> MeasureError:
        """Build from an error object ``{"code", "message", "retryable"}`` (contract 1.1)."""
        return cls(err["code"], err.get("message"), err.get("retryable"))

    def to_dict(self) -> dict[str, Any]:
        """The contract error object: ``{"code", "message", "retryable"}``."""
        return errors.error_object(self.code, self.message) | {"retryable": self.retryable}

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return f"MeasureError(code={self.code!r}, message={self.message!r}, retryable={self.retryable!r})"


def measure(address: str, *, lat: float | None = None, lng: float | None = None, method: str = "auto",
            verify: bool = True, force: bool = False, deadline_s: float = 180.0, cache_dir: str | Path,
            work_dir: str | Path | None = None, anthropic_api_key: str | None = None,
            google_solar_api_key: str | None = None, overpass_urls: Sequence[str] | None = None,
            on_stage: Callable[[str], None] | None = None, isolate: bool = True,
            blocks_path: str | Path | None = None, solar_fixture: str | Path | None = None) -> dict[str, Any]:
    """Measure one roof and return the ``bond.roof_model/0.2`` envelope as a dict.

    Blocks the calling thread for up to ``deadline_s`` plus ``KILL_GRACE_S`` (30) seconds: run it off a request
    thread and off a serial worker loop. Keys and directories are arguments; once ``measure`` runs, the process
    environment is not consulted for keys (``anthropic_api_key=None`` means no verifier, never "use the env").

    ``address`` is geocoded unless ``lat`` and ``lng`` are both given (then it may be ""). ``method`` is "auto"
    (LiDAR, falling back to ``solar_agent`` when both keys are given), "lidar_skeleton", "lidar_agent" or
    "solar_agent". ``verify=True`` without an Anthropic key yields verdict "unverified", not an error. ``force``
    bypasses the on-disk fetch cache for this call. ``cache_dir`` (required) holds fetched bodies; see
    ``purge_cache``. ``work_dir`` keeps the files the pipeline writes (``<slug>_blocks.json``, ``<slug>_model.json``,
    transcripts); None uses a temporary directory removed afterwards. ``isolate=True`` runs the pipeline in a
    child process killed at ``deadline_s + KILL_GRACE_S``; ``isolate=False`` runs it in this thread (no kill
    possible, fine for tests and scripts).

    ``on_stage(name)`` is called in the caller's thread, in order, with names from ``STAGES``. Names may be skipped
    or repeat; "geocode" is emitted even when coordinates are given. A callback that raises aborts the call.
    A result whose warnings contain ``source_unreachable`` is degraded by a data-source outage: retry later.

    Raises ``ValueError`` for bad arguments (unknown method, only one of lat/lng, out-of-range coordinates,
    ``deadline_s`` <= 0 or not finite, blank address without coordinates, a missing ``blocks_path`` or
    ``solar_fixture`` file). Raises ``MeasureError`` for the job codes: address_not_found, no_footprint,
    ambiguous_building, no_lidar_coverage, lidar_too_sparse, measurement_failed (also a crashed child),
    upstream_unavailable, timeout (also a killed child). ``interrupted`` is never raised here.

    ``blocks_path`` and ``solar_fixture`` are test hooks: they replace LiDAR/Solar with a fixture file, so the
    call needs no network (verify=False) and no real address.
    """
    lat_lng = _check(address, lat, lng, method, deadline_s, blocks_path, solar_fixture, overpass_urls)
    cache_path = Path(cache_dir).resolve()  # absolute: the child must not depend on its working directory
    cache_path.mkdir(parents=True, exist_ok=True)
    own_dir = work_dir is None
    work = Path(tempfile.mkdtemp(prefix="roof_measure_")) if own_dir else Path(work_dir).resolve()  # type: ignore[arg-type]
    try:
        work.mkdir(parents=True, exist_ok=True)
        req: dict[str, Any] = {
            "address": (address or "").strip(), "lat_lng": lat_lng, "method": method, "verify": bool(verify),
            "force": bool(force), "deadline_s": float(deadline_s), "work_dir": str(work),
            "blocks_path": str(Path(blocks_path).resolve()) if blocks_path else None,
            "solar_fixture": str(Path(solar_fixture).resolve()) if solar_fixture else None,
            "runtime": {"cache_dir": str(cache_path), "anthropic_api_key": anthropic_api_key,
                        "google_solar_api_key": google_solar_api_key,
                        "overpass_urls": list(overpass_urls) if overpass_urls else None,
                        "footprint_stage_s": None},
        }
        if isolate:
            from ._isolate import run_isolated
            return run_isolated(req, on_stage, grace=KILL_GRACE_S)
        return _run_in_process(req, on_stage)
    finally:
        if own_dir:
            shutil.rmtree(work, ignore_errors=True)


def purge_cache(cache_dir: str | Path, days: float = 30.0) -> int:
    """Delete fetched bodies and stray temp files in ``cache_dir`` older than ``days``; returns how many.

    ``measure`` never purges: the caller schedules this (for example daily).
    """
    from . import cache
    with config.use(config.Runtime(cache_dir=Path(cache_dir))):
        return cache.purge_old(days)


def _check(address: str | None, lat: float | None, lng: float | None, method: str, deadline_s: float,
           blocks_path: str | Path | None, solar_fixture: str | Path | None,
           overpass_urls: Sequence[str] | None = None) -> list[float] | None:
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    if address is not None and not isinstance(address, str):
        raise ValueError("address must be a string")
    if isinstance(overpass_urls, str):
        raise ValueError("overpass_urls must be a sequence of URLs, not a string")  # noqa: TRY004 - D2
    if (lat is None) != (lng is None):
        raise ValueError("lat and lng must be given together")
    lat_lng = None
    if lat is not None and lng is not None:
        if isinstance(lat, (bool, str, bytes)) or isinstance(lng, (bool, str, bytes)):
            raise ValueError("lat and lng must be numbers")
        try:
            flat, flng = float(lat), float(lng)
        except (TypeError, ValueError):
            raise ValueError("lat and lng must be numbers") from None
        if not (math.isfinite(flat) and math.isfinite(flng) and -90 <= flat <= 90 and -180 <= flng <= 180):
            raise ValueError("lat must be finite in -90..90 and lng finite in -180..180")
        lat_lng = [flat, flng]
    elif not (address or "").strip():
        raise ValueError("address must not be blank when lat/lng are not given")
    if isinstance(deadline_s, bool) or not (isinstance(deadline_s, (int, float)) and math.isfinite(deadline_s)
                                            and deadline_s > 0):
        raise ValueError("deadline_s must be a finite number greater than 0")
    for name, p in (("blocks_path", blocks_path), ("solar_fixture", solar_fixture)):
        if p is not None and not Path(p).is_file():
            raise ValueError(f"{name} is not an existing file: {p}")
    return lat_lng


def _run_in_process(req: dict[str, Any], on_stage: Callable[[str], None] | None) -> dict[str, Any]:
    """Run the pipeline in this thread; every failure becomes a ``MeasureError`` (callback errors propagate)."""
    from . import cache
    from .deadline import Deadline
    from .pipeline import run_pipeline

    raised: list[BaseException] = []

    def stage(name: str) -> None:
        try:
            (on_stage or (lambda _n: None))(name)
        except BaseException as exc:  # re-raised untouched after the pipeline unwinds
            raised.append(exc)
            raise

    rt = req["runtime"]
    runtime = config.Runtime(cache_dir=Path(rt["cache_dir"]), anthropic_api_key=rt["anthropic_api_key"],
                             google_solar_api_key=rt["google_solar_api_key"],
                             overpass_urls=tuple(rt["overpass_urls"]) if rt["overpass_urls"] else None)
    try:
        with config.use(runtime), cache.force_scope(req["force"]):
            res = run_pipeline(req["address"], req["work_dir"], req["method"], blocks_path=req["blocks_path"],
                               solar_fixture=req["solar_fixture"], deadline=Deadline.after(req["deadline_s"]),
                               lat_lng=tuple(req["lat_lng"]) if req["lat_lng"] else None, on_stage=stage,
                               verify=req["verify"], render=False)
        try:
            json.dumps(res.envelope, allow_nan=False)
        except ValueError:
            raise MeasureError("measurement_failed", "the envelope contains non-finite numbers") from None
        return res.envelope
    except MeasureError:
        raise
    except Exception as exc:
        if raised:
            raise raised[0] from None
        raise MeasureError.from_error(errors.error_from(exc)) from exc
