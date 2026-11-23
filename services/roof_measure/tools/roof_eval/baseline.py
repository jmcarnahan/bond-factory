"""roof-baseline: freeze a run's results and metrics under <data>/baselines/<name>. Needs CONFIRM (never silent)."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from . import SCORER_VERSION

KEEP = ("fit_all", "fit_covered", "coverage", "facets", "area_sqft", "overlap_sqft", "perimeter_ft", "ridge_hip_ft")


def freeze(run_dir: Path, bdir: Path, confirm: bool, manifest: Path | None = None) -> Path:
    """Copy <run>/results/*.json to <bdir>/results and write <bdir>/metrics.json (per-house result sha256 and key
    metrics, the run summary). An existing baseline is moved aside, never deleted. Refuses without ``confirm``."""
    if not confirm:
        raise SystemExit(f"refusing to freeze {bdir.name!r}: a baseline is never changed silently, pass CONFIRM=1")
    summary = json.loads((run_dir / "summary.json").read_text())
    recs = [json.loads(ln) for ln in (run_dir / "per_house.jsonl").read_text().splitlines() if ln.strip()]
    if bdir.exists():
        shutil.move(str(bdir), str(bdir.with_name(f"{bdir.name}.replaced-{time.strftime('%Y%m%d-%H%M%S')}")))
    (bdir / "results").mkdir(parents=True)
    per: dict[str, Any] = {}
    for r in recs:
        src = run_dir / "results" / f"{r['id']}.json"
        entry: dict[str, Any] = {"status": r.get("status"), "verdict": r.get("verdict")}
        if src.is_file():
            shutil.copy(src, bdir / "results" / src.name)
            entry["sha256"] = hashlib.sha256(src.read_bytes()).hexdigest()
        entry.update({k: (r.get("m") or {}).get(k) for k in KEEP})
        per[r["id"]] = entry
    meta = {"name": bdir.name, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "scorer": SCORER_VERSION,
            "engine": summary["engine"], "split": summary["split"], "n": summary["n"], "digest": summary["digest"],
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest and manifest.is_file() else None,
            "overall": summary["overall"], "t3": summary.get("t3"), "per_house": per}
    (bdir / "metrics.json").write_text(json.dumps(meta, indent=1, sort_keys=True, default=float))
    return bdir
