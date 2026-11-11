"""Run one measurement in a child interpreter with a whitelisted environment and a hard kill."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .library import MeasureError

CHILD_ENV_KEYS = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "PYTHONPATH", "VIRTUAL_ENV",
                  "PYTHONHOME", "LD_LIBRARY_PATH", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
                  "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy", "SYSTEMROOT")
CHILD_ENV_CAPS = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                  "RAYON_NUM_THREADS": "2", "MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1"}


def _child_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in CHILD_ENV_KEYS if k in os.environ}
    env.update(CHILD_ENV_CAPS)
    return env


def _child_argv() -> list[str]:
    return [sys.executable, "-P", "-m", "roof_measure._child"]  # -P: the working directory stays off sys.path


def _stderr_tail(path: Path) -> str:
    try:
        lines = path.read_text(errors="replace").strip().splitlines()[-10:]
    except OSError:
        return ""
    text = "\n".join(lines)[-1000:]
    return f"; stderr: {text}" if text else ""


def _read(proc: subprocess.Popen, q: queue.Queue) -> None:
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            try:
                msg = json.loads(line)
            except ValueError:
                continue  # stray non-JSON output from a library
            if isinstance(msg, dict) and "t" in msg:
                q.put(msg)
    finally:
        q.put({"t": "eof"})


def run_isolated(req: dict[str, Any], on_stage: Callable[[str], None] | None, grace: float) -> dict[str, Any]:
    """Start the child, relay its stages to ``on_stage`` in this thread, return its envelope or raise MeasureError."""
    stderr_path = Path(req["work_dir"]) / "child.stderr"
    errfile = open(stderr_path, "wb")  # noqa: SIM115 - closed in finally
    proc = None
    reader = None
    try:
        proc = subprocess.Popen(_child_argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errfile,
                                env=_child_env(), text=True, bufsize=1)
        try:
            proc.stdin.write(json.dumps(req) + "\n")  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]
        except OSError:
            pass  # the child died early; the eof branch reports it
        q: queue.Queue = queue.Queue()
        reader = threading.Thread(target=_read, args=(proc, q), daemon=True)
        reader.start()
        limit = time.monotonic() + req["deadline_s"] + grace
        while True:
            left = limit - time.monotonic()
            if left <= 0:
                proc.kill()
                proc.wait()
                raise MeasureError("timeout", f"the measurement process was stopped after "
                                              f"{req['deadline_s'] + grace:.0f} s", retryable=True)
            try:
                msg = q.get(timeout=min(0.5, left))
            except queue.Empty:
                continue
            kind = msg.get("t")
            if kind == "stage":
                if on_stage is not None:
                    on_stage(msg["name"])
            elif kind == "ok":
                try:
                    json.dumps(msg["envelope"], allow_nan=False)
                except ValueError:
                    raise MeasureError("measurement_failed", "the envelope contains non-finite numbers") from None
                try:
                    proc.wait(5)  # let a normally exiting child finish before the finally's kill
                except subprocess.TimeoutExpired:
                    pass
                return msg["envelope"]
            elif kind == "err":
                raise MeasureError.from_error(msg["error"])
            elif kind == "eof":
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise MeasureError("measurement_failed", f"the measurement process exited with code "
                                                         f"{proc.returncode}" + _stderr_tail(stderr_path))
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        errfile.close()
        if reader is not None:
            reader.join(timeout=5)
        if proc is not None and proc.stdout is not None:
            proc.stdout.close()
