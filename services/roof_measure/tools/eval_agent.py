"""Rule method versus the agent on saved LiDAR block files: one table row per file, the pictures beside.

    ANTHROPIC_API_KEY=... .venv/bin/python -m tools.eval_agent <blocks.json>... [--out DIR] [--no-agent]

For each ``bond.roof_blocks`` file: the rule result (offline) and one live agent run (``lidar_agent``, which itself
returns the rule result when the agent's roof fits the planes worse). Prints plane mismatch, uncovered share, the model
area against the planes' area, blocks, wall seconds, API calls and tokens. With ``--out`` each run's model JSON and a
side-by-side PNG (``tools/eval_png.py``) are written. Spends API calls: one run per file. The key is read from the
environment only and never printed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from roof_measure import pipeline


def one(path: Path, out: Path, method: str) -> dict[str, Any]:
    t0 = time.monotonic()
    row: dict[str, Any] = {"file": path.stem, "method": method}
    try:
        res = pipeline.run_pipeline("x", out / f"{path.stem}_{method}", method, blocks_path=path, verify=False)
    except Exception as exc:  # noqa: BLE001 - a crash is the one result this tool exists to catch
        row.update(error=f"{type(exc).__name__}: {' '.join(str(exc).split())[:100]}", seconds=round(time.monotonic() - t0, 1))
        return row
    q = res.model.get("quality") or {}
    planes = res.model.get("planes") or []
    plane_area = sum(p["surface_area_sqft"] for p in planes)
    usage = (res.agent_transcript or {}).get("usage") or {}
    row.update(used=res.method_used, mismatch=q.get("plane_mismatch_pct"), uncovered=q.get("model_uncovered_pct"),
               model_sqft=round(res.model["totals"]["total_area_sqft"]), planes_sqft=round(plane_area),
               blocks=len(res.model["blocks"]), facets=len(res.model["facets"]),
               valid=not res.model["source"].get("planes_only"), seconds=round(time.monotonic() - t0, 1),
               calls=(res.agent_transcript or {}).get("api_calls"),
               tokens=(usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                       + usage.get("cache_creation_input_tokens", 0), usage.get("output_tokens", 0)),
               codes=[c for c in res.envelope["warning_codes"] if c in ("agent_failed_fell_back", "model_failed")],
               dir=str(out / f"{path.stem}_{method}"))
    return row


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("blocks", nargs="+")
    ap.add_argument("--out", default="out_eval_agent")
    ap.add_argument("--no-agent", action="store_true", help="the rule result only (no API calls)")
    a = ap.parse_args(argv)
    out = Path(a.out)
    rows = []
    for f in map(Path, a.blocks):
        for method in ("lidar_skeleton",) + (() if a.no_agent else ("lidar_agent",)):
            row = one(f, out, method)
            rows.append(row)
            print(json.dumps(row, default=str), flush=True)
            if "dir" in row:
                d = Path(row["dir"])
                model = next(d.glob("*_model.json"), None)
                blocks = next(d.glob("*_blocks.json"), None)
                if model and blocks and row.get("valid"):
                    import subprocess

                    subprocess.run([sys.executable, str(Path(__file__).with_name("eval_png.py")), str(model), str(blocks),
                                    str(out / f"{f.stem}_{method}.png"), f"{f.stem} {method}"], check=False)
    return 1 if any("error" in r for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
