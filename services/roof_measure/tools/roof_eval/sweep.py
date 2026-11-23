"""roof-sweep: run an engine over a list of house dirs with no truth; tabulate automation, verdicts, parcel match, failures.

``--houses`` is a directory of house dirs (each with points_wide.npy, footprint.json, optional meta.json) or a text file
with one house dir per line. Reference points are derived in memory (nothing is written into those dirs).
"""

from __future__ import annotations

import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from . import data, engines, price, runner, stats, tables


def house_dirs(spec: Path) -> list[Path]:
    if spec.is_dir():
        return sorted(p for p in spec.iterdir() if (p / "points_wide.npy").is_file())
    return sorted(Path(ln.strip()) for ln in spec.read_text().splitlines() if ln.strip() and not ln.startswith("#"))


def _err_class(r: dict[str, Any]) -> str:
    lines = (r.get("error") or r["engine"]["stderr_tail"] or r["engine"]["status"]).strip().splitlines()
    return (lines[-1] if lines else r["engine"]["status"])[:80]


def sweep(cfg: runner.Config, houses: Path, limit: int | None = None) -> dict[str, Any]:
    """Run, score truth-free, write per_house.jsonl, summary.json and tables.md under ``cfg.out_dir``."""
    t0 = time.monotonic()
    dirs = house_dirs(houses)[: limit or None]
    if not dirs:
        raise SystemExit(f"no house dirs under {houses}")
    name, template = engines.resolve_engine(cfg.engine)
    cfg.trusted = name in engines.TRUSTED
    rules = price.load_rules(cfg.price_rules)
    with ThreadPoolExecutor(max_workers=max(1, cfg.jobs)) as ex:
        recs = list(ex.map(lambda d: runner.process_house(cfg, template, {"id": d.name}, rules, d), dirs))
    for r, d in zip(recs, dirs, strict=True):
        r["row"]["parcel_match"] = (data.load_json(d / "meta.json", {}) or {}).get("parcel_match")
    recs.sort(key=lambda r: r["id"])
    rt = [r["runtime_s"] for r in recs]
    summary: dict[str, Any] = {"engine": name, "mode": "sweep", "n": len(recs), "split": "sweep", "scorer": runner.SCORER_VERSION,
                               "wall_s": round(time.monotonic() - t0, 1), "digest": runner.digest(recs), **tables.aggregate_all(recs), "ok": True,
                               "runtime": {"median_s": stats.median(rt), "p90_s": stats.percentile(rt, 90), "total_s": sum(rt)},
                               "error_classes": dict(Counter(_err_class(r) for r in recs if r["engine"]["status"] != "ok"
                                                             or r.get("status") == "score_error"))}
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    (cfg.out_dir / "per_house.jsonl").write_text("".join(runner.canonical(r) + "\n" for r in recs))
    (cfg.out_dir / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=float))
    (cfg.out_dir / "tables.md").write_text(tables.render(summary, recs))
    return summary
