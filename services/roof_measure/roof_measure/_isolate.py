"""Run one measurement in a child interpreter with a whitelisted environment and a hard kill."""

from __future__ import annotations

import contextlib
import json
import os
import queue
import signal
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


AGENT_HANG_EXIT = 4  # the child stops itself with this code when the agent stage outlives its time budget


class ChildCrashed(MeasureError):
    """The child process died on a signal (a native crash such as a segfault in CGAL) or stopped itself because the
    agent stage hung past its time budget (exit code ``AGENT_HANG_EXIT``), not with an error reply.

    ``signal_number`` is the signal; the message names it and carries the end of the child's stderr, where
    ``faulthandler`` (enabled in ``_child``) left the Python traceback of the crash.
    """

    def __init__(self, code: str = "measurement_failed", message: str | None = None, retryable: bool | None = None,
                 *, signal_number: int = 0) -> None:
        super().__init__(code, message, retryable)  # same positional signature as MeasureError: copy and pickle work
        self.signal_number = signal_number


def _stderr_tail(path: Path) -> str:
    """The last lines of the child's stderr; when faulthandler wrote a crash report, start at its first line."""
    try:
        all_lines = path.read_text(errors="replace").strip().splitlines()
    except OSError:
        return ""
    fatal = [i for i, ln in enumerate(all_lines) if ln.startswith("Fatal Python error")]
    if fatal:  # keep the head: "Fatal Python error: ..." and the first frames, whatever the paths' length
        text = "\n".join(all_lines[fatal[-1]:][:12])[:1000]
    else:
        text = "\n".join(all_lines[-10:])[-1000:]
    return f"; stderr: {text}" if text else ""


def _exit_text(returncode: int | None) -> str:
    """``exited with code -11 (SIGSEGV, Segmentation fault)`` for a signal death, plain ``exited with code 3``."""
    if returncode is not None and returncode < 0:
        try:
            sig = signal.Signals(-returncode)
            return f"exited with code {returncode} ({sig.name}, {signal.strsignal(sig)})"
        except ValueError:
            pass
    return f"exited with code {returncode}"


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
        try:
            proc = subprocess.Popen(_child_argv(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errfile,
                                    env=_child_env(), text=True, bufsize=1)
        except OSError as exc:
            raise MeasureError("measurement_failed", f"could not start the measurement process: {exc}") from exc
        try:
            proc.stdin.write(json.dumps(req) + "\n")  # type: ignore[union-attr]
            proc.stdin.close()  # type: ignore[union-attr]
        except OSError:
            with contextlib.suppress(OSError):  # the child died early; the eof branch reports it
                proc.stdin.close()  # type: ignore[union-attr]
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
                text = f"the measurement process {_exit_text(proc.returncode)}" + _stderr_tail(stderr_path)
                if proc.returncode == AGENT_HANG_EXIT:
                    raise ChildCrashed("measurement_failed", "the measurement process was stopped: the agent stage "
                                       "did not finish within its time budget (a native hang)" + _stderr_tail(stderr_path))
                if proc.returncode is not None and proc.returncode < 0:
                    raise ChildCrashed("measurement_failed", text, signal_number=-proc.returncode)
                raise MeasureError("measurement_failed", text)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
        errfile.close()
        if proc is not None and proc.stdin is not None:
            with contextlib.suppress(OSError):
                proc.stdin.close()
        if reader is not None:
            reader.join(timeout=5)
        if proc is not None and proc.stdout is not None and not (reader is not None and reader.is_alive()):
            proc.stdout.close()
