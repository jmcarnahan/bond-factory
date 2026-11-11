"""Cost and latency spike for the verifier: python -m tools.spike_verifier --fixtures

With ANTHROPIC_API_KEY set it runs verify() live on the synthetic fixtures and prints tokens, dollars and
seconds per roof. Without a key it prints the deterministic verdicts and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from roof_measure.verify import verify

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
NAMES = ("synthetic_hip", "synthetic_gable", "synthetic_flat_parapet", "synthetic_hip_zigzag")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true", help="run on the synthetic fixtures")
    ap.parse_args()
    live = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not live:
        print("no key: deterministic only")
    print(f"{'fixture':<26}| verdict    | rounds | input_tok | output_tok | usd     | seconds | area_sqft")
    for name in NAMES:
        path = FIXTURES / f"{name}.json"
        if not path.exists():
            print(f"{name:<26}| (missing, skipped)")
            continue
        t0 = time.monotonic()
        res = verify(json.loads(path.read_text()))
        v = res.verification
        u = v["usage"]
        usd = u["input_tokens"] * 2e-6 + u["output_tokens"] * 1e-5
        print(f"{name:<26}| {v['verdict']:<10} | {v['rounds']:<6} | {u['input_tokens']:<9} | {u['output_tokens']:<10} "
              f"| {usd:<7.4f} | {time.monotonic() - t0:<7.1f} | {res.model['totals']['total_area_sqft']:.1f}")
        for n in v["notes"]:
            print(f"    note: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
