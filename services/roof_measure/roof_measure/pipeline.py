"""The measuring pipeline: address -> footprint -> LiDAR -> plane engine -> model -> 0.2 envelope.

``run_pipeline`` is synchronous. The caller passes a ``Deadline`` (every stage checks it), ``lat_lng`` (skips the
geocoder) and ``on_stage`` (progress). The data-layer modules are imported lazily inside the stages.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .deadline import Deadline
from .pipeline_result import PipelineResult
from .pipeline_stages import PipelineError, parse_address  # noqa: F401  (re-exported: callers import these from here)


def _noop(_stage: str) -> None:
    return None


def run_pipeline(address: str, out_dir: str | Path, method: str = "lidar_skeleton", *,
                 deadline: Deadline | None = None, lat_lng: tuple[float, float] | None = None,
                 on_stage: Callable[[str], None] | None = None, include_other_buildings: bool = False,
                 building_outline_id: str | None = None, pinned: bool = True,
                 points_path: str | Path | None = None, hints: dict[str, Any] | None = None) -> PipelineResult:
    """Run the whole pipeline for one address; writes ``<slug>_{model,engine}.json`` into ``out_dir``.

    ``method`` is ``auto`` or ``lidar_skeleton`` (the same thing: the plane engine on live LiDAR).
    ``building_outline_id``: measure exactly that county outline (``FootprintError`` when it does not exist).
    ``pinned``: a given ``lat_lng`` is the caller's rooftop point (default), so the parcel and outline that hold it are
    chosen; False when it is only a street geocode.
    ``points_path``: offline hook: a regression-set house folder (``points_wide.npy``, ``footprint.json``,
    ``meta.json``) read instead of the geocoder, footprint chain and LiDAR fetch.
    """
    if method not in ("auto", "lidar_skeleton"):
        raise PipelineError("the plane engine runs on live LiDAR with method 'auto' or 'lidar_skeleton'")
    from .engine.hints import clean_hints, params_from_hints
    from .pipeline_engine import run_planes

    extra = {}
    if (clean := clean_hints(hints)) is not None:  # no hint: the call is exactly what it always was
        extra = {"params": params_from_hints(clean), "hints": clean}
    res = run_planes(address, out_dir, deadline=deadline, lat_lng=lat_lng, on_stage=on_stage or _noop,
                     building_outline_id=building_outline_id, pinned=pinned, points_path=points_path, **extra)
    if include_other_buildings:  # lot.py: the other buildings on the parcel, measured by the same engine (additive keys)
        from .lot import add_other_buildings

        add_other_buildings(res, address=address, lat_lng=lat_lng, deadline=deadline, out_dir=out_dir, pinned=pinned)
    return res
