"""Library facade: ``measure()`` returns the ``bond.roof_model/0.2`` envelope, ``MeasureError`` carries the job codes.

Imports only the standard library, ``errors`` and ``config`` at module level, so ``import roof_measure`` stays light.
"""

from __future__ import annotations

import json
import math
import shutil
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import config, errors

STAGES = ("geocode", "footprint", "lidar", "model")
KILL_GRACE_S = 30.0
LOT_RETRY_MIN_S = 30.0  # a crashed child is retried without the other buildings only with this much time left


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


def measure(address: str, *, lat: float | None = None, lng: float | None = None, force: bool = False, deadline_s: float = 180.0, cache_dir: str | Path,
            work_dir: str | Path | None = None, overpass_urls: Sequence[str] | None = None,
            on_stage: Callable[[str], None] | None = None, isolate: bool = True,
            include_other_buildings: bool = False, building_outline_id: str | None = None,
            points_path: str | Path | None = None) -> dict[str, Any]:
    """Measure one roof with the plane engine and return the ``bond.roof_model/0.2`` envelope as a dict (0.7.0 keys).

    Blocks the calling thread for up to ``deadline_s`` plus ``KILL_GRACE_S`` (30) seconds: run it off a request
    thread and off a serial worker loop. Keys and directories are arguments; the process environment is not consulted.

    ``address`` is geocoded unless ``lat`` and ``lng`` are both given (then it may be ""). ``force`` bypasses the on-disk fetch cache for this call. ``cache_dir`` (required, created if
    missing) holds fetched bodies; see ``purge_cache``. ``work_dir`` keeps the files the pipeline writes
    (``<slug>_model.json``, ``<slug>_engine.json``); None uses a temporary directory removed afterwards.
    ``isolate=True`` runs the pipeline in a child process killed at ``deadline_s + KILL_GRACE_S``; ``isolate=False``
    runs it in this thread (no kill possible, fine for tests and scripts).

    ``on_stage(name)`` is called in the caller's thread, in order, with names from ``STAGES``. Names may be skipped
    or repeat; "geocode" is emitted even when coordinates are given. A callback that raises aborts the call.
    A result whose warnings contain ``source_unreachable`` is degraded by a data-source outage: retry later.

    Raises ``ValueError`` for bad arguments (only one of lat/lng, out-of-range
    coordinates, ``deadline_s`` <= 0 or not finite, blank address without coordinates, a ``work_dir`` or
    ``cache_dir`` that is a file). Raises ``MeasureError`` for the job codes: address_not_found, no_footprint,
    ambiguous_building, no_lidar_coverage, lidar_too_sparse, measurement_failed (also a crashed child),
    upstream_unavailable, timeout (also a killed child).

    ``include_other_buildings=True`` also measures the other buildings of the parcel (county outlines of at least
    120 sq ft, same engine, inside the same deadline) and adds the optional envelope key ``other_buildings`` and the
    ``lot_*`` totals (contract-0.3, section "Other buildings"). The default changes nothing.
    A building that cannot be measured is recorded with ``status`` ``failed`` and never fails the main result.

    ``lat``/``lng`` is taken as the roof's own point: the county parcel that contains it, and the outline on that
    parcel that contains or is nearest to it, are measured. ``building_outline_id`` (a county outline id from an
    earlier result's ``model.source.building.outline_id``) measures exactly that outline instead; an unknown id raises
    ``MeasureError`` ``no_footprint`` and the chain never substitutes another building.

    ``points_path`` is the offline test hook: a house folder with ``points_wide.npy`` (x, y, z, ASPRS class in a
    local metric frame, z absolute), ``footprint.json`` (``{"polygon": [[x, y], ...]}`` in the same frame) and
    ``meta.json`` (``frame`` {crs_epsg, x0_m, y0_m}, ``outline_source``, ``parcel_match``, ``lidar``). No network is
    used and ``address`` may be blank.
    """
    lat_lng = _check(address, lat, lng, deadline_s, overpass_urls, work_dir, cache_dir, points_path)
    cache_path = Path(cache_dir).resolve()  # absolute: the child must not depend on its working directory
    cache_path.mkdir(parents=True, exist_ok=True)
    own_dir = work_dir is None
    work = Path(tempfile.mkdtemp(prefix="roof_measure_")) if own_dir else Path(work_dir).resolve()  # type: ignore[arg-type]
    try:
        work.mkdir(parents=True, exist_ok=True)
        req: dict[str, Any] = {
            "address": (address or "").strip(), "lat_lng": lat_lng,
            "force": bool(force), "deadline_s": float(deadline_s), "work_dir": str(work),
            "include_other_buildings": bool(include_other_buildings),
            "building_outline_id": str(building_outline_id).strip() if building_outline_id else None,
            "points_path": str(Path(points_path).resolve()) if points_path else None,
            "runtime": {"cache_dir": str(cache_path),
                        "overpass_urls": list(overpass_urls) if overpass_urls else None,
                        "footprint_stage_s": None},
        }
        if isolate:
            from ._isolate import ChildCrashed, run_isolated
            started = time.monotonic()
            seen: list[str] = []

            def tracked(name: str) -> None:
                seen.append(name)
                if on_stage is not None:
                    on_stage(name)

            try:
                return run_isolated(req, tracked, grace=KILL_GRACE_S)
            except ChildCrashed as crash:
                return _retry_after_crash(req, on_stage, crash, started, seen)
        return _run_in_process(req, on_stage)
    finally:
        if own_dir:
            shutil.rmtree(work, ignore_errors=True)


def _retry_after_crash(req: dict[str, Any], on_stage: Callable[[str], None] | None, crash: MeasureError,
                       started: float, seen: Sequence[str] = ()) -> dict[str, Any]:
    """A child that died while ``include_other_buildings`` was on is retried once without it (the extra buildings
    are an addition, never a new way to fail); the result says so with an ``other`` warning. Any other crash, too
    little time left, or a retry that fails raises the first crash itself (a retry that times out never hides it)."""
    from . import _isolate

    left = req["deadline_s"] - (time.monotonic() - started)
    if not req.get("include_other_buildings") or left < LOT_RETRY_MIN_S:
        raise crash
    done = set(seen)

    def fresh(name: str) -> None:
        if name not in done and on_stage is not None:
            on_stage(name)

    try:
        env = _isolate.run_isolated({**req, "include_other_buildings": False, "deadline_s": left}, fresh,
                                    grace=KILL_GRACE_S)
    except MeasureError as retry_error:  # includes a second crash and a timeout
        raise crash from retry_error
    env["warnings"] = [*env.get("warnings", []),
                       "The other buildings on the parcel could not be measured (the measurement process crashed)."]
    env["warning_codes"] = [*env.get("warning_codes", []), "other"]
    return env


def purge_cache(cache_dir: str | Path, days: float = 30.0) -> int:
    """Delete fetched bodies and stray temp files in ``cache_dir`` older than ``days``; returns how many.

    ``measure`` never purges: the caller schedules this (for example daily).
    """
    from . import cache
    with config.use(config.Runtime(cache_dir=Path(cache_dir))):
        return cache.purge_old(days)


def _check(address: str | None, lat: float | None, lng: float | None, deadline_s: float,
           overpass_urls: Sequence[str] | None = None, work_dir: str | Path | None = None,
           cache_dir: str | Path | None = None, points_path: str | Path | None = None) -> list[float] | None:
    if points_path and (not (Path(points_path) / "points_wide.npy").is_file()
                        or not (Path(points_path) / "footprint.json").is_file()):
        raise ValueError(f"points_path must be a house folder with points_wide.npy and footprint.json: {points_path}")
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
    elif not (address or "").strip() and not points_path:
        raise ValueError("address must not be blank when lat/lng are not given")
    if isinstance(deadline_s, bool) or not (isinstance(deadline_s, (int, float)) and math.isfinite(deadline_s)
                                            and deadline_s > 0):
        raise ValueError("deadline_s must be a finite number greater than 0")
    for name, d in (("work_dir", work_dir), ("cache_dir", cache_dir)):
        if d is not None and Path(d).is_file():
            raise ValueError(f"{name} must be a directory, not a file: {d}")
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
    runtime = config.Runtime(cache_dir=Path(rt["cache_dir"]),
                             overpass_urls=tuple(rt["overpass_urls"]) if rt["overpass_urls"] else None)
    try:
        with config.use(runtime), cache.force_scope(req["force"]):
            res = run_pipeline(req["address"], req["work_dir"], deadline=Deadline.after(req["deadline_s"]),
                               lat_lng=tuple(req["lat_lng"]) if req["lat_lng"] else None, on_stage=stage,
                               include_other_buildings=bool(req.get("include_other_buildings")),
                               building_outline_id=req.get("building_outline_id"),
                               points_path=req.get("points_path"))
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
