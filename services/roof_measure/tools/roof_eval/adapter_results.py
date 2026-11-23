"""Adapter ``results-dir``: copy an existing result.json (e.g. a research candidate) into the engine output slot.

Usage: python -m tools.roof_eval.adapter_results <house_dir> <out_json> --results-dir DIR [--slug-map FILE]
Looks for DIR/<id>/result.json, DIR/<id>.json, then (with a slug map id -> slug or {slug: ...}, or
$ROOF_EVAL_SLUG_MAP) DIR/<slug>/result.json and DIR/<slug>.json. Exit 3 when nothing is found.
Research results call a height jump ``step``; here it becomes ``level_change``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def find_result(results_dir: Path, hid: str, slug_map: dict | None = None) -> Path | None:
    names = [hid]
    if slug_map and hid in slug_map:
        v = slug_map[hid]
        names.append(v.get("slug") if isinstance(v, dict) else str(v))
    for n in names:
        for cand in (results_dir / n / "result.json", results_dir / f"{n}.json"):
            if cand.is_file():
                return cand
    return None


def normalise(res: dict, hid: str) -> dict:
    res = dict(res)
    res["slug"] = hid
    res["edges"] = [{**e, "type": "level_change" if e.get("type") == "step" else e.get("type")}
                    for e in res.get("edges") or []]
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("house_dir")
    ap.add_argument("out_json")
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--slug-map", default=os.environ.get("ROOF_EVAL_SLUG_MAP"))
    a = ap.parse_args(argv)
    hid = Path(a.house_dir).name
    sm = json.loads(Path(a.slug_map).read_text()) if a.slug_map else None
    src = find_result(Path(a.results_dir), hid, sm)
    if src is None:
        print(f"no result for {hid} in {a.results_dir}", file=sys.stderr)
        return 3
    Path(a.out_json).write_text(json.dumps(normalise(json.loads(src.read_text()), hid)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
