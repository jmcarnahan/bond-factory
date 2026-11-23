"""The roof-eval run: engine on every house of a split (parallel), score, write per_house.jsonl, summary.json, tables.md.

Deterministic: houses are processed in id order, the output sorts by id, and ``digest`` (sha256 over every house's
canonical result and truth-free metrics, runtime excluded) is identical on two runs of a deterministic engine.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import SCORER_VERSION, compare, data, engines, gates, m_truth, price, score, tables, validate


@dataclass
class Config:
    root: Path
    out_dir: Path
    engine: str | None = None
    split: str = "tuning"
    where: list[str] = field(default_factory=list)
    jobs: int = 4
    baseline: str | None = None
    gates_file: Path | None = None
    price_rules: Path | None = None
    timeout_s: int = engines.DEFAULT_TIMEOUT_S
    limit: int | None = None
    baselines_dir: Path | None = None
    trusted: bool = False  # engine may read the real house dir (library adapter only; set by evaluate)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=float)


def _strata(row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    keep = {k: row.get(k) for k in ("split", "roof_class", "region", "complexity", "density_band", "pitch_band",
                                    "flags", "tiers", "dup_group", "facet_count_ref", "facet_count_src", "density_pts_m2", "canary")}
    keep["parcel_match"] = row.get("parcel_match") or meta.get("parcel_match")
    keep["pooled"] = data.pooled_stratum(row) if row.get("roof_class") else None
    return keep


def process_house(cfg: Config, template: str, row: dict[str, Any], rules: dict[str, Any] | None,
                  hdir: Path | None = None) -> dict[str, Any]:
    """Run the engine on one house and score the result; never raises (failures become a record with an error).
    ``hdir`` set (roof-sweep): a house outside the regression set, no truth, reference points kept in memory."""
    hid = row["id"]
    own = hdir is None
    hdir = hdir or data.house_dir(cfg.root, hid)
    out_json = cfg.out_dir / "results" / f"{hid}.json"
    run = engines.run_engine(template, hdir, out_json, cfg.timeout_s, cfg.trusted)
    rec: dict[str, Any] = {"id": hid, "row": _strata(row, data.load_json(hdir / "meta.json", {}) or {}),
                           "engine": {k: run[k] for k in ("status", "returncode", "stderr_tail")},
                           "runtime_s": round(run["runtime_s"], 3)}
    try:
        res, bad = None, []
        if out_json.is_file():
            try:
                res = json.loads(out_json.read_text())
            except ValueError as exc:
                bad = [f"not JSON: {exc}"]
            else:
                bad = validate.problems(res)
        if bad:  # malformed output is "invalid", distinct from a refusal (a valid result with no facets)
            rec.update({"status": "invalid", "automation": False, "automation_ok": False, "verdict": None, "invalid_reasons": bad})
            res = None
        else:
            ref = data.reference_points(hdir, write=own)
            rec.update(score.score_house(res, ref, data.parse_polygon(data.load_json(hdir / "footprint.json")),
                                         data.load_truths(cfg.root, hid) if own else [], rules, row.get("facet_count_ref")))
            if res is not None:
                rec["result_sha"] = hashlib.sha256(canonical(res).encode()).hexdigest()[:16]
    except Exception as exc:  # noqa: BLE001  a scoring failure is data, not a crash of the whole run
        rec.update({"status": "score_error", "automation": False, "automation_ok": False, "verdict": None,
                    "error": f"{type(exc).__name__}: {exc}"})
    rec["invalid_or_crashed"] = int(rec.get("status") in ("invalid", "no_result", "score_error"))
    return rec


def run_houses(cfg: Config, rows: list[dict[str, Any]], template: str) -> list[dict[str, Any]]:
    rules = price.load_rules(cfg.price_rules)
    with ThreadPoolExecutor(max_workers=max(1, cfg.jobs)) as ex:
        recs = list(ex.map(lambda r: process_house(cfg, template, r, rules), rows))
    return sorted(recs, key=lambda r: r["id"])


def digest(recs: list[dict[str, Any]]) -> str:
    """sha256 over each house's id, status, result hash and truth-free metrics (no runtimes, no paths)."""
    items = [[r["id"], r.get("status"), r.get("result_sha"), r.get("m"), r.get("truth")] for r in recs]
    return hashlib.sha256(canonical(items).encode()).hexdigest()


def write_outputs(cfg: Config, recs: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    with (cfg.out_dir / "per_house.jsonl").open("w") as fh:
        for r in recs:
            fh.write(canonical(r) + "\n")
    (cfg.out_dir / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True, default=float))
    (cfg.out_dir / "tables.md").write_text(tables.render(summary, recs))


def library_t3(cfg: Config, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The T3 aggregate of ENGINE=library on the same rows (gate 7b when the data root ships no frozen library baseline).
    None when the houses carry no stored envelope."""
    _, template = engines.resolve_engine("library")
    lib = Config(**{**cfg.__dict__, "engine": "library", "out_dir": cfg.out_dir / "onthefly-library", "trusted": True,
                    "gates_file": None, "baseline": None})
    recs = run_houses(lib, [r for r in rows if not data.is_canary(r)], template)
    t3 = m_truth.t3_aggregate(recs)
    return t3 if t3 and t3.get("iqr") else None


def evaluate(cfg: Config) -> dict[str, Any]:
    """Run, score, compare with the baseline, evaluate the gates; returns the summary (``summary["ok"]`` False on failure)."""
    rows = data.select_rows(data.load_manifest(cfg.root), cfg.split, cfg.where)
    if cfg.limit:
        rows = rows[: cfg.limit]
    if not rows:
        raise SystemExit(f"no houses in split {cfg.split!r} (where={cfg.where}) under {cfg.root}")
    stale = data.check_references(cfg.root, [r["id"] for r in rows])
    if stale:
        raise data.StaleReference(f"{len(stale)} of {len(rows)} houses have a reference not made by rule {data.REF_RULE}/{data.REF_HASH} "
                                  f"(e.g. {stale[0]}); refusing to score. Rebuild with {data.REBUILD_CMD}")
    name, template = engines.resolve_engine(cfg.engine)
    cfg.trusted = name in engines.TRUSTED
    if (cfg.out_dir / "results").is_dir():
        shutil.rmtree(cfg.out_dir / "results")
    t0 = time.monotonic()
    recs = run_houses(cfg, rows, template)
    summary: dict[str, Any] = {"scorer": SCORER_VERSION, "engine": name, "split": cfg.split, "where": cfg.where,
                               "n": len(recs), "wall_s": round(time.monotonic() - t0, 1), "digest": digest(recs),
                               **tables.aggregate_all(recs), "ok": True}
    if cfg.price_rules:
        rules = price.load_rules(cfg.price_rules) or {}
        summary["price_rules"] = {"file": cfg.price_rules.name, "example": cfg.price_rules.name.endswith("example.json") or "FAKE" in str(rules.get("_note", ""))}
    if cfg.baseline:
        bdir = (cfg.baselines_dir or cfg.root / "baselines") / cfg.baseline
        summary["compare"] = compare.compare_to_baseline(cfg, recs, bdir)
        summary["ok"] &= summary["compare"]["pass"]
    if cfg.gates_file:
        spec = json.loads(cfg.gates_file.read_text())
        bdir = cfg.baselines_dir or cfg.root / "baselines"
        cache: dict[str, Any] = {}

        def baseline_t3(name: str) -> dict[str, Any] | None:
            t3 = (data.load_json(bdir / name / "metrics.json", {}) or {}).get("t3")
            if t3 and t3.get("iqr"):
                return t3
            if "onthefly" not in cache:  # no frozen baseline: the library on the same houses, computed now
                cache["onthefly"] = library_t3(cfg, rows)
            return cache["onthefly"]

        summary["gates"] = gates.evaluate(spec, recs, baseline_t3)
        summary["ok"] &= all(g["passed"] for g in summary["gates"])
    write_outputs(cfg, recs, summary)
    return summary


def check_twice(cfg: Config) -> tuple[bool, str, str, bool]:
    """Run the whole evaluation twice into ``<out>`` and ``<out>-2``; (identical, digest 1, digest 2, all gates and
    comparisons passed in both runs). A failed gate must never hide behind identical digests."""
    a = evaluate(cfg)
    cfg2 = Config(**{**cfg.__dict__, "out_dir": cfg.out_dir.with_name(cfg.out_dir.name + "-2")})
    b = evaluate(cfg2)
    return a["digest"] == b["digest"], a["digest"], b["digest"], bool(a["ok"] and b["ok"])
