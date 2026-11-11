"""The job service: validates a request, answers from the result cache or queues a job."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .deadline import Deadline
from .errors import error_object
from .jobs import JobRunner, JobStore
from .keys import alias_key, request_key
from .results import ResultCache
from .settings import Settings

log = logging.getLogger("roof_measure.service")
RunFn = Callable[[dict[str, Any], Path, Deadline, Callable[[str], None]], dict[str, Any]]


class Service:
    def __init__(self, settings: Settings, run: RunFn | None = None, watchdog_grace_s: float | None = None):
        self.settings = settings
        self.store = JobStore(settings.data_dir)
        self.results = ResultCache(settings.data_dir)
        if run is None:
            from .runner import make_run
            run = make_run(settings, self.results)
        self._lock = threading.Lock()
        self._inflight: dict[str, list[str]] = {}  # request key -> [leader job id, follower ids...]
        kw = {} if watchdog_grace_s is None else {"watchdog_grace_s": watchdog_grace_s}
        self.runner = JobRunner(self.store, settings.workers, settings.queue_max, settings.job_timeout_s, run,
                                settings.retention_days, on_done=self._resolve_followers,
                                extra_purge=self._purge_caches, **kw)
        self.store.purge(settings.retention_days)
        self._purge_caches()
        n = self.store.mark_interrupted_on_boot()
        if n:
            log.warning("marked %d interrupted job(s) failed on boot", n)

    def _purge_caches(self) -> None:
        """Cached results (retention days) and fetch-cache bodies (30 days): at boot and hourly after a job."""
        self.results.purge(self.settings.retention_days)
        try:
            from . import cache
            cache.purge_old(30.0)
        except OSError:
            log.warning("fetch cache purge failed")

    def cached(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """A finished envelope for this request without running anything, or None."""
        key = request_key(req)
        if key is None:
            key = self.results.alias_get(alias_key(req))
        return self.results.get(key) if key else None

    def submit(self, req: dict[str, Any]) -> dict[str, Any]:
        """Create the job and return its record; ``status`` is ``done`` on a cache hit. Raises QueueFull.

        Identical requests in flight are coalesced: followers get their own id and resolve with the leader's
        outcome, so five simultaneous POSTs run the pipeline once. ``force`` always runs on its own.
        """
        hit = None if req.get("force") else self.cached(req)
        if hit is not None:
            job = self.store.create(req)
            self.store.write_result(job["id"], hit)
            log.info("job done id=%s cache_hit=true", job["id"])
            return self.store.update(job["id"], status="done")
        key = None if req.get("force") else (request_key(req) or alias_key(req))
        with self._lock:
            if key is not None and key in self._inflight:
                job = self.store.create(req)
                self._inflight[key].append(job["id"])
                log.info("job queued id=%s coalesced_with=%s", job["id"], self._inflight[key][0])
                return job
            self.runner.reserve()  # raises QueueFull before anything is written
            try:
                job = self.store.create(req)
            except BaseException:
                self.runner.release()
                raise
            if key is not None:
                self._inflight[key] = [job["id"]]
        self.runner.submit(job["id"], reserved=True)
        return job

    def _resolve_followers(self, leader_id: str) -> None:
        """Called when a job ends (done, failed or watchdog timeout): copy its outcome to coalesced followers."""
        with self._lock:
            key = next((k for k, ids in self._inflight.items() if ids[0] == leader_id), None)
            followers = self._inflight.pop(key)[1:] if key else []
        if not followers:
            return
        leader = self.store.get(leader_id) or {}
        result = self.store.read_result(leader_id) if leader.get("status") == "done" else None
        for fid in followers:
            if result is not None:
                self.store.write_result(fid, result)
                self.store.update(fid, status="done", stage=None)
            else:
                self.store.update(fid, status="failed", stage=None, error=leader.get("error") or error_object(
                    "measurement_failed"))

    def view(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get(job_id)
        if job is None:
            return None
        out: dict[str, Any] = {"id": job["id"], "status": job["status"]}
        if job["status"] == "running" and job.get("stage"):
            out["stage"] = job["stage"]
        if job["status"] == "failed":
            out["error"] = job["error"]
        if job["status"] == "done":
            result = self.store.read_result(job_id)
            if result is None:
                out.update(status="failed", error={"code": "measurement_failed", "retryable": False,
                                                   "message": "The stored result could not be read."})
            else:
                out["result"] = result
        return out
