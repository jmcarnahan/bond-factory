"""Offline evaluation of the rule method on saved LiDAR block files: one table row per file.

Run (from services/roof_measure): ``make eval BLOCKS=<file-or-dir> [ARGS="--json out.json --svg out_dir"]``
or ``.venv/bin/python -m tools.eval_blocks <file-or-dir>... [--json FILE] [--svg DIR]``.

No network, no keys, no verifier: each blocks JSON goes through the library's ``blocks_path`` hook. Files that are not
``bond.roof_blocks/0.1`` documents (the envelope fixtures beside them) are skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from roof_measure.classify import BLOCKS_SCHEMA
from roof_measure.library import MeasureError, measure

COLUMNS = ("file", "planes", "facets", "mismatch%", "covered%", "uncov%", "spread ft", "model sqft", "planes sqft", "pitch m/p", "reasons")


def blocks_files(paths: list[str]) -> list[Path]:
    """Every blocks JSON under the given files and directories (directories one level deep, sorted)."""
    out: list[Path] = []
    for p in map(Path, paths):
        for f in sorted(p.glob("*.json")) if p.is_dir() else [p]:
            try:
                if json.loads(f.read_text()).get("schema") == BLOCKS_SCHEMA:
                    out.append(f)
            except (OSError, ValueError, AttributeError):
                continue
    return out


def evaluate(path: Path, cache_dir: Path) -> dict[str, Any]:
    """The envelope of one blocks file (rule method, offline) or ``{"error": code}``."""
    try:
        env = measure("", lat=0.0, lng=0.0, method="lidar_skeleton", verify=False, cache_dir=cache_dir,
                      blocks_path=path, isolate=False)
    except (MeasureError, ValueError) as exc:
        return {"file": path.name, "error": str(exc)}
    return {"file": path.name, "envelope": env}


def _fmt(v: Any) -> str:
    return "-" if v is None else str(v)


def _sqft(v: Any) -> str:
    return "-" if v is None else f"{v:,.0f}"


def row(res: dict[str, Any]) -> list[str]:
    """The table cells of one result (see ``COLUMNS``)."""
    if "error" in res:
        return [res["file"], *["-"] * 9, f"error: {res['error']}"[:60]]
    env = res["envelope"]
    q = env["model"].get("quality") or {}
    t = env["totals"]
    pitch = f"{t['predominant_pitch']:.1f}/{_fmt(t.get('planes_pitch_weighted'))}"
    return [res["file"], _fmt(q.get("planes_lidar")), _fmt(q.get("facets_model", t["facets"])),
            _fmt(q.get("plane_mismatch_pct")), _fmt(q.get("outline_covered_pct")), _fmt(q.get("model_uncovered_pct")),
            _fmt(q.get("level_spread_ft")), f"{t['area_sqft']:,.0f}",
            _sqft(t.get("planes_surface_area_sqft")), pitch, ",".join(q.get("reasons") or []) or "-"]


def table(rows: list[list[str]]) -> str:
    """Left-aligned fixed-width table with a header."""
    cells = [list(COLUMNS), *rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(COLUMNS))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip() for r in cells)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="blocks JSON files or directories of them")
    ap.add_argument("--json", metavar="FILE", help="write every envelope's metrics here")
    ap.add_argument("--svg", metavar="DIR", help="write <name>.svg (model left, snapped planes right) per file")
    ap.add_argument("--envelopes", metavar="DIR", help="write each full envelope as <name>.envelope.json")
    args = ap.parse_args(argv)
    files = blocks_files(args.paths)
    if not files:
        print("no bond.roof_blocks/0.1 files found", file=sys.stderr)
        return 2
    results = []
    with tempfile.TemporaryDirectory(prefix="eval_blocks_") as cache:
        for f in files:
            results.append(evaluate(f, Path(cache)))
    print(table([row(r) for r in results]))
    if args.json:
        Path(args.json).write_text(json.dumps([
            {"file": r["file"], **({"error": r["error"]} if "error" in r else {
                "quality": r["envelope"]["model"].get("quality"), "totals": r["envelope"]["totals"],
                "warning_codes": r["envelope"]["warning_codes"], "method_used": r["envelope"]["method_used"]})}
            for r in results], indent=1) + "\n")
    for out_dir in (args.envelopes, args.svg):
        if out_dir:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
    for f, r in zip(files, results, strict=True):
        if "error" in r:
            continue
        if args.envelopes:
            (Path(args.envelopes) / f"{f.stem}.envelope.json").write_text(json.dumps(r["envelope"], indent=1) + "\n")
        if args.svg:
            from tools.eval_svg import side_by_side

            ring = json.loads(f.read_text())["footprint_ft"]
            (Path(args.svg) / f"{f.stem}.svg").write_text(side_by_side(r["envelope"], ring, f.stem))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
