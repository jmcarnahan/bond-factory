"""Job store on disk and a bounded worker pool (plan D3).

``DATA_DIR/jobs/<id>/job.json`` is the record, ``result.json`` the envelope. Every write is tmp + ``os.replace``.
One replica only: the store is not shared between processes. On boot, jobs left ``queued`` or ``running`` by a
previous process become ``failed`` with code ``interrupted``.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .deadline import Deadline
from .errors import error_from, error_object

log = logging.getLogger("roof_measure.jobs")
ID_RE = re.compile(r"[0-9a-f]{32}")
ACTIVE = ("queued", "running")


class QueueFull(RuntimeError):
    """The bounded queue has no room; the API answers 429."""


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_dir(path: Path) -> Path:
    """mkdir -p, with a log line that names the fix when the volume is not writable (Railway: root-owned)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("cannot create %s (%s). On Railway the /data volume is root-owned: set RAILWAY_RUN_UID=0 on the "
                  "service (the container then runs as root), or make DATA_DIR writable by the container user.",
                  path, type(exc).__name__)
        raise
    return path


def write_json_atomic(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, suffix=".tmp", delete=False) as tmp:
        try:
            json.dump(obj, tmp, allow_nan=False)  # a NaN total must fail the job, not poison the stored result
        except BaseException:
            Path(tmp.name).unlink(missing_ok=True)
            raise
    os.replace(tmp.name, path)


class JobStore:
    def __init__(self, data_dir: str | Path):
        self.root = ensure_dir(Path(data_dir) / "jobs")
        self._lock = threading.Lock()

    def job_dir(self, job_id: str) -> Path:
        if not ID_RE.fullmatch(job_id):
            raise KeyError(job_id)
        return self.root / job_id

    def create(self, request: dict[str, Any]) -> dict[str, Any]:
        job = {"id": uuid.uuid4().hex, "status": "queued", "stage": None, "created_at": now_iso(),
               "updated_at": now_iso(), "request": request, "error": None}
        with self._lock:
            write_json_atomic(self.job_dir(job["id"]) / "job.json", job)
        return job

    def get(self, job_id: str) -> dict[str, Any] | None:
        try:
            doc = json.loads((self.job_dir(job_id) / "job.json").read_text())
        except (KeyError, FileNotFoundError, ValueError):
            return None
        if not isinstance(doc, dict) or not isinstance(doc.get("status"), str):
            log.warning("ignoring malformed job record %s", job_id)
            return None
        return doc

    def update(self, job_id: str, **fields: Any) -> dict[str, Any]:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job.update(fields, updated_at=now_iso())
            write_json_atomic(self.job_dir(job_id) / "job.json", job)
            return job

    def write_result(self, job_id: str, result: dict[str, Any]) -> None:
        write_json_atomic(self.job_dir(job_id) / "result.json", result)

    def read_result(self, job_id: str) -> dict[str, Any] | None:
        try:
            return json.loads((self.job_dir(job_id) / "result.json").read_text())
        except (KeyError, FileNotFoundError, ValueError):
            return None

    def list_incomplete(self) -> list[dict[str, Any]]:
        jobs = (self.get(p.name) for p in sorted(self.root.iterdir()) if p.is_dir())
        return [j for j in jobs if j and j["status"] in ACTIVE]

    def purge(self, days: float, now: float | None = None) -> int:
        """Delete finished job dirs whose ``job.json`` is older than ``days`` days; returns how many."""
        cutoff = (time.time() if now is None else now) - days * 86400
        removed = 0
        for tmp in self.root.glob("*/*.tmp"):  # a crash between write and replace leaves these behind
            try:
                if tmp.stat().st_mtime < (time.time() if now is None else now) - 3600:
                    tmp.unlink()
            except OSError:
                continue
        for d in sorted(self.root.iterdir()):
            job = self.get(d.name) if d.is_dir() else None
            if job is None or job["status"] in ACTIVE:
                continue
            try:
                if (d / "job.json").stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed

    def mark_interrupted_on_boot(self) -> int:
        stale = self.list_incomplete()
        for j in stale:
            self.update(j["id"], status="failed", stage=None, error=error_object("interrupted"))
        return len(stale)


# run(job, out_dir, deadline, on_stage) -> envelope dict; raises on failure
RunFn = Callable[[dict[str, Any], Path, Deadline, Callable[[str], None]], dict[str, Any]]
WATCHDOG_GRACE_S = 30.0
EXTRA_PURGE_EVERY_S = 3600.0


class JobRunner:
    """Bounded pool. The job deadline is cooperative (every fetch and stage checks it, see CLAUDE.md); the
    watchdog is the backstop: a job still running ``watchdog_grace_s`` past its deadline is marked failed with code
    ``timeout`` even if its thread is stuck (the thread itself cannot be killed and keeps its worker slot)."""

    def __init__(self, store: JobStore, workers: int, queue_max: int, timeout_s: float, run: RunFn,
                 retention_days: float = 14.0, on_done: Callable[[str], None] | None = None,
                 watchdog_grace_s: float = WATCHDOG_GRACE_S, extra_purge: Callable[[], None] | None = None):
        self.store, self.queue_max, self.timeout_s, self.run = store, queue_max, timeout_s, run
        self.retention_days, self.on_done, self.grace_s = retention_days, on_done, watchdog_grace_s
        self.workers = max(1, workers)
        self.extra_purge, self._last_extra_purge = extra_purge, time.monotonic()  # results + fetch cache, hourly
        self._pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="roof-job")
        self._queued = 0
        self._running = 0
        self._active: dict[str, float] = {}  # job id -> monotonic time at which the watchdog gives up
        self._abandoned: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._watch, name="roof-watchdog", daemon=True).start()

    def reserve(self) -> None:
        """Take a queue slot before the job exists, so a refused request leaves nothing on disk.

        ``queue_max`` is the number of jobs that may wait; 0 means no waiting: a job is admitted only when a
        worker is free."""
        with self._lock:
            if len(self._abandoned) >= self.workers:
                raise QueueFull  # every worker is stuck on an abandoned job: nothing would ever run
            if self._queued >= self.queue_max and self._queued + self._running >= self.workers:
                raise QueueFull
            self._queued += 1

    @property
    def abandoned_workers(self) -> int:
        """Workers still held by a job the watchdog gave up on (their threads cannot be killed)."""
        with self._lock:
            return len(self._abandoned)

    def release(self) -> None:
        with self._lock:
            self._queued -= 1

    def submit(self, job_id: str, reserved: bool = False) -> None:
        if not reserved:
            self.reserve()
        self._pool.submit(self._work, job_id)

    def shutdown(self) -> None:
        self._stop.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _finish(self, job_id: str) -> None:
        if self.on_done:
            try:
                self.on_done(job_id)
            except Exception:
                log.exception("on_done failed for job %s", job_id)

    def _watch(self) -> None:
        while not self._stop.wait(min(1.0, max(0.05, self.grace_s / 4))):
            now = time.monotonic()
            with self._lock:
                late = [j for j, at in self._active.items() if now > at and j not in self._abandoned]
                self._abandoned.update(late)
            with self._lock:
                all_stuck = len(self._abandoned) >= self.workers
            if all_stuck:  # queued jobs would wait forever: fail them now (retryable)
                for j in self.store.list_incomplete():
                    if j["status"] == "queued":
                        self.store.update(j["id"], status="failed", stage=None, error=error_object("timeout"))
                        self._finish(j["id"])
            for job_id in late:
                log.warning("job watchdog: id=%s did not finish %gs after its deadline; marking timeout", job_id,
                            self.grace_s)
                try:
                    self.store.update(job_id, status="failed", stage=None, error=error_object("timeout"))
                except KeyError:
                    pass
                self._finish(job_id)

    def _claim(self, job_id: str) -> bool:
        """Take ownership of the job's outcome. False when the watchdog already reported a timeout.

        Atomic with the watchdog's scan: once claimed the job leaves ``_active``, so the watchdog can no longer
        fail it, and a job the watchdog flagged can no longer be completed."""
        with self._lock:
            if job_id in self._abandoned:
                return False
            self._active.pop(job_id, None)
            return True

    def _work(self, job_id: str) -> None:
        with self._lock:
            self._queued -= 1
            self._running += 1
            self._active[job_id] = time.monotonic() + self.timeout_s + self.grace_s
        started = time.monotonic()
        try:
            current = self.store.get(job_id)
            if current is None or current["status"] != "queued":
                return  # failed while it waited (all workers were stuck): nothing to run
            job = self.store.update(job_id, status="running", stage="start")
            deadline = Deadline.after(self.timeout_s)
            result = self.run(job, self.store.job_dir(job_id), deadline,
                              lambda stage: self._stage(job_id, stage))
            if not self._claim(job_id):
                return  # the watchdog already reported a timeout; do not overwrite it
            self.store.write_result(job_id, result)
            self.store.update(job_id, status="done", stage=None)
            log.info("job done id=%s ms=%d", job_id, int((time.monotonic() - started) * 1000))
        except Exception as exc:  # any failure becomes a coded job error; the detail stays out of INFO logs
            if not self._claim(job_id):
                return
            err = error_from(exc)
            log.warning("job failed id=%s code=%s exc=%s ms=%d", job_id, err["code"], type(exc).__name__,
                        int((time.monotonic() - started) * 1000))
            log.debug("job %s failure detail: %s", job_id, exc, exc_info=True)  # may hold an address or a path
            try:
                self.store.update(job_id, status="failed", stage=None, error=err)
            except Exception:
                log.exception("could not record failure for job %s", job_id)
        finally:
            with self._lock:
                self._running -= 1
                self._active.pop(job_id, None)
                abandoned = job_id in self._abandoned
                self._abandoned.discard(job_id)
            if not abandoned:
                self._finish(job_id)
            self._purge()

    def _stage(self, job_id: str, stage: str) -> None:
        with self._lock:  # never write a stage onto a job the watchdog already failed
            if job_id not in self._abandoned:
                self.store.update(job_id, stage=stage)

    def _purge(self) -> None:
        try:
            n = self.store.purge(self.retention_days)
            if n:
                log.info("purged %d job dir(s) older than %g days", n, self.retention_days)
            if self.extra_purge and time.monotonic() - self._last_extra_purge >= EXTRA_PURGE_EVERY_S:
                self._last_extra_purge = time.monotonic()
                self.extra_purge()
        except OSError:
            log.exception("retention purge failed")
