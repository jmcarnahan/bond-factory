"""Child process of ``measure(isolate=True)``: ``python -P -m roof_measure._child``.

Reads one JSON request line on stdin, replies with JSON lines on a private copy of stdout: ``{"t":"stage",..}``,
then ``{"t":"ok","envelope":{..}}`` or ``{"t":"err","error":{..}}``. Everything a library prints goes to stderr.
Keys arrive in the request, never in env or argv. The child exits when its parent dies.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, TextIO

CAPS = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "RAYON_NUM_THREADS": "2",
        "MPLBACKEND": "Agg"}
_PROTO: TextIO | None = None  # the protocol stream: a private copy of the original stdout


def _emit(obj: dict[str, Any]) -> None:
    try:
        text = json.dumps(obj, allow_nan=False)
    except ValueError:
        text = json.dumps({"t": "err", "error": {"code": "measurement_failed", "retryable": False,
                                                 "message": "the envelope contains non-finite numbers"}})
    out = _PROTO or sys.stdout
    out.write(text + "\n")
    out.flush()


def _watch_parent(ppid: int, interval: float = 0.5, getppid=os.getppid, die=os._exit) -> None:
    """Exit (code 3) as soon as the parent changes: an orphaned child must not run on."""
    while True:
        time.sleep(interval)
        if getppid() != ppid:
            die(3)


def _start_watchdog() -> threading.Thread:
    t = threading.Thread(target=_watch_parent, args=(os.getppid(),), daemon=True)
    t.start()
    return t


def main() -> int:
    global _PROTO
    _PROTO = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)  # any print from a library lands on stderr, never in the protocol stream
    sys.stdout = sys.stderr
    _start_watchdog()
    line = sys.stdin.readline()
    if not line.strip():
        return 2  # the parent went away before sending a request
    req = json.loads(line)
    for k, v in CAPS.items():
        os.environ.setdefault(k, v)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    from . import cache, config, errors
    from .deadline import Deadline
    from .pipeline import run_pipeline

    rt = req["runtime"]
    runtime = config.Runtime(cache_dir=Path(rt["cache_dir"]), anthropic_api_key=rt["anthropic_api_key"],
                             google_solar_api_key=rt["google_solar_api_key"],
                             overpass_urls=tuple(rt["overpass_urls"]) if rt["overpass_urls"] else None)
    log = logging.getLogger("roof_measure")
    try:
        with config.use(runtime), cache.force_scope(req["force"]):
            res = run_pipeline(req["address"], req["work_dir"], req["method"], blocks_path=req["blocks_path"],
                               solar_fixture=req["solar_fixture"], deadline=Deadline.after(req["deadline_s"]),
                               lat_lng=tuple(req["lat_lng"]) if req["lat_lng"] else None,
                               on_stage=lambda s: _emit({"t": "stage", "name": s}), verify=req["verify"],
                               render=False)
        _emit({"t": "ok", "envelope": res.envelope})
    except Exception as exc:
        log.warning("measurement failed: %s", type(exc).__name__)  # no traceback at WARNING: urls hold the address
        log.debug("measurement failed", exc_info=True)
        _emit({"t": "err", "error": errors.error_from(exc)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
