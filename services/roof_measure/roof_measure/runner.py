"""The job body: geocode, check the result cache, run the pipeline, store the envelope.

Logging is structured ``key=value`` lines: job id, stage, elapsed ms, footprint source, cache hit. The address
is never logged at INFO and the bearer token never reaches this module.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .deadline import Deadline
from .envelope import build_envelope
from .keys import alias_key, matched_key, request_key
from .results import ResultCache
from .settings import Settings

log = logging.getLogger("roof_measure.runner")


def _fixture(settings: Settings, name: str | None) -> Path | None:
    from .api import fixture_path

    return fixture_path(settings, name)


def envelope_from_fixture(settings: Settings, name: str | None) -> dict[str, Any]:
    """Debug ``method: "fixture"``: a saved 0.2 envelope, or a bare 0.1 model wrapped as unverified."""
    path = _fixture(settings, name or "roof_measurement_0.2_pass.json")
    doc = json.loads(path.read_text())  # type: ignore[union-attr]
    if "contract" in doc:
        return doc
    verification = {"verdict": "unverified", "notes": ["Fixture model wrapped without verification."],
                    "adjustments": [], "original_totals": {}, "model": None, "rounds": 0,
                    "usage": {"input_tokens": 0, "output_tokens": 0}}
    return build_envelope(doc, method_used=doc["source"]["method"], footprint_source="osm", verification=verification,
                          warnings=["Fixture model wrapped without verification."],
                          warning_codes=["verifier_unverified"])


def run_measurement(req: dict[str, Any], out_dir: Path, deadline: Deadline, on_stage: Callable[[str], None],
                    settings: Settings, results: ResultCache, job_id: str = "-") -> dict[str, Any]:
    """The job body, with every HTTP fetch (geocoder included) bound to the job's deadline."""
    from . import cache

    with cache.deadline_scope(deadline):
        return _run_measurement(req, out_dir, deadline, on_stage, settings, results, job_id)


def _run_measurement(req: dict[str, Any], out_dir: Path, deadline: Deadline, on_stage: Callable[[str], None],
                     settings: Settings, results: ResultCache, job_id: str) -> dict[str, Any]:
    from . import geocode
    from .pipeline import run_pipeline

    started = time.monotonic()
    if req["method"] == "fixture":
        env = envelope_from_fixture(settings, req.get("fixture"))
        _store(results, request_key(req), req, None, env)
        return env
    lat_lng = (req["lat"], req["lng"]) if req.get("lat") is not None else None
    lat_lng_given = lat_lng is not None  # a pin must not become the alias of a plain address (S3)
    key = request_key(req)
    if key is None:  # address only: the key is the geocoder's matched address (plan D4)
        on_stage("geocode")
        deadline.check("geocode")
        g = geocode.geocode(req["address"])
        lat_lng, key = (g.lat, g.lng), matched_key(g.formatted, req)
    if not req.get("force"):
        hit = results.get(key)
        if hit is not None:
            if not lat_lng_given:
                results.alias_put(alias_key(req), key)
            log.info("job=%s stage=cache_hit cache_hit=true ms=%d", job_id, int((time.monotonic() - started) * 1000))
            return hit
    else:
        from . import cache
        cache.force_refresh(True)  # this job's fetches skip the on-disk HTTP cache (see cache.py)
    try:
        res = run_pipeline(req["address"], out_dir, req["method"], blocks_path=_fixture(settings, req.get("blocks_fixture")),
                           solar_fixture=_fixture(settings, req.get("solar_fixture")), deadline=deadline,
                           lat_lng=lat_lng, on_stage=on_stage, verify=req["verify"], no_agent=False)
    finally:
        if req.get("force"):
            cache.force_refresh(False)
    if res.transient:
        log.info("job=%s result not cached: a data source was unreachable", job_id)
    else:
        _store(results, key, req, None if lat_lng_given else alias_key(req), res.envelope)
    log.info("job=%s stage=done footprint_source=%s cache_hit=false ms=%d", job_id, res.footprint_source,
             int((time.monotonic() - started) * 1000))
    return res.envelope


def _store(results: ResultCache, key: str | None, req: dict[str, Any], alias: str | None,
           env: dict[str, Any]) -> None:
    if key is None:
        return
    results.put(key, env)
    if alias:
        results.alias_put(alias, key)


def make_run(settings: Settings, results: ResultCache):
    def run(job: dict[str, Any], out_dir: Path, deadline: Deadline, on_stage: Callable[[str], None]) -> dict[str, Any]:
        return run_measurement(job["request"], out_dir, deadline, on_stage, settings, results, job["id"])

    return run
