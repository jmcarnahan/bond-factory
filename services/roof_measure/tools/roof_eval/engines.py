"""Engines are commands: ``<cmd> {house_dir} {out_json}``. One run writes a CONTRACT-1 result.json at ``out_json``.

An engine NEVER sees the real house dir: it runs on a temporary copy holding only points_wide.npy, points.npy,
footprint.json and a minimal meta.json (frame, outline_source, parcel_match). No reference points, stored envelope,
truth or baselines are in it. Only the ``library`` adapter (which converts a stored library result by design) is trusted
with the real dir.

``--engine library`` (or ``library:ground``) and ``--engine results-dir:<dir>`` expand to the two adapters in this package;
anything else is taken as a command template (split like a shell line, no shell is used). ``$ROOF_EVAL_ENGINE``
is the default.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PKG_ROOT = Path(__file__).resolve().parents[2]  # services/roof_measure: cwd so `-m tools...` resolves
DEFAULT_TIMEOUT_S = 900
ENGINE_FILES = ("points_wide.npy", "points.npy", "footprint.json")
META_KEYS = ("frame", "outline_source", "parcel_match")
TRUSTED = ("library", "library-ground")  # adapters that read the stored envelope


def sanitised_copy(hdir: Path, tmp: Path) -> Path:
    """``tmp/<house id>/`` with only what an engine may read (see the module doc)."""
    dst = tmp / hdir.name
    dst.mkdir(parents=True)
    for f in ENGINE_FILES:
        if (hdir / f).is_file():
            shutil.copy(hdir / f, dst / f)
    try:
        meta = json.loads((hdir / "meta.json").read_text())
    except (OSError, ValueError):
        meta = {}
    (dst / "meta.json").write_text(json.dumps({k: meta[k] for k in META_KEYS if k in meta}))
    return dst


def resolve_engine(spec: str | None) -> tuple[str, str]:
    """(short name, command template) for a ``--engine`` value or ``$ROOF_EVAL_ENGINE``."""
    spec = spec or os.environ.get("ROOF_EVAL_ENGINE", "")
    if not spec:
        raise SystemExit("no engine: pass --engine library | results-dir:<dir> | '<cmd> {house_dir} {out_json}' "
                         "or set ROOF_EVAL_ENGINE")
    py = shlex.quote(sys.executable)
    if spec == "oracle":  # the exact synthetic roof as a result (scorer self-test; houses must be named after synth cases)
        return "oracle", f"{py} -m tools.roof_eval.synth {{house_dir}} {{out_json}}"
    if spec in ("library", "library:ground"):  # library:ground = datum from the ground ring, not from roof points
        extra = " --datum ground" if spec.endswith("ground") else ""
        return spec.replace(":", "-"), f"{py} -m tools.roof_eval.adapter_library {{house_dir}} {{out_json}}{extra}"
    if spec.startswith("results-dir:"):
        d = spec.split(":", 1)[1]
        return "results-dir", f"{py} -m tools.roof_eval.adapter_results {{house_dir}} {{out_json}} --results-dir {shlex.quote(d)}"
    if "{house_dir}" not in spec or "{out_json}" not in spec:
        raise SystemExit("an engine command must contain {house_dir} and {out_json}")
    return shlex.split(spec)[0].rsplit("/", 1)[-1], spec


def run_engine(template: str, hdir: Path, out_json: Path, timeout_s: int = DEFAULT_TIMEOUT_S,
               trusted: bool = False) -> dict[str, Any]:
    """Run the engine once on a sanitised copy of the house dir (``trusted``: the real dir, library adapter only).
    Returns status (ok|failed|timeout|no_output), runtime_s, returncode, stderr_tail."""
    if trusted:
        return _run(template, hdir, out_json, timeout_s)
    with tempfile.TemporaryDirectory(prefix="roof_eval_") as tmp:
        return _run(template, sanitised_copy(hdir, Path(tmp)), out_json, timeout_s)


def _run(template: str, hdir: Path, out_json: Path, timeout_s: int) -> dict[str, Any]:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    if out_json.exists():
        out_json.unlink()
    argv = [t.format(house_dir=str(hdir), out_json=str(out_json)) for t in shlex.split(template)]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(PKG_ROOT), os.environ.get("PYTHONPATH", "")]).rstrip(os.pathsep)}
    t0 = time.monotonic()
    try:
        p = subprocess.run(argv, check=False, cwd=PKG_ROOT, env=env, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "runtime_s": time.monotonic() - t0, "returncode": None, "stderr_tail": ""}
    except OSError as exc:
        return {"status": "failed", "runtime_s": time.monotonic() - t0, "returncode": None, "stderr_tail": str(exc)}
    tail = "\n".join(p.stderr.strip().splitlines()[-5:])[-600:]
    status = "ok" if out_json.is_file() else ("failed" if p.returncode else "no_output")
    return {"status": status, "runtime_s": time.monotonic() - t0, "returncode": p.returncode, "stderr_tail": tail}
