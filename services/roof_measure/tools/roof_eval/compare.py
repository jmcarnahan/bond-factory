"""Paired comparison of a run with a frozen baseline.

The baseline's stored result.json files are scored again with the CURRENT scorer on the same reference points, so a scorer
change never looks like an engine change. A house is flagged when its area changes by more than 3%, its facet count by
more than 2, ``fit_all`` drops by more than 0.05, an overlap appears (over 1 sqft), or a result is lost. The comparison
FAILS when more than 5% of the paired houses are flagged or the median |area change| exceeds 1%.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import data, score, stats

DEFAULTS = {"area_pct": 3.0, "facets": 2, "fit_all_drop": 0.05, "overlap_sqft": 1.0, "flag_share": 0.05,
            "median_area_pct": 1.0}


def thresholds(cfg) -> dict[str, float]:
    t = dict(DEFAULTS)
    if cfg.gates_file:
        t.update((json.loads(Path(cfg.gates_file).read_text()).get("compare")) or {})
    return t


def baseline_record(cfg, bdir: Path, rec: dict[str, Any]) -> dict[str, Any] | None:
    f = bdir / "results" / f"{rec['id']}.json"
    res = data.load_json(f) if f.is_file() else None
    if res is None:
        return None
    hdir = data.house_dir(cfg.root, rec["id"])
    return score.score_house(res, data.reference_points(hdir), data.parse_polygon(data.load_json(hdir / "footprint.json")), [])


def compare_to_baseline(cfg, recs: list[dict[str, Any]], bdir: Path) -> dict[str, Any]:
    """Paired comparison; houses absent from the baseline are ignored, houses that lost their result are flagged."""
    if not bdir.is_dir():
        raise SystemExit(f"baseline {bdir.name!r} not found under {bdir.parent}")
    th = thresholds(cfg)
    flagged, paired, area_changes, reasons = [], 0, [], {}
    for r in recs:
        b = baseline_record(cfg, bdir, r)
        if b is None or not b.get("m"):
            continue
        paired += 1
        why = []
        if not r.get("m"):
            why.append("lost_result")
        else:
            m, bm = r["m"], b["m"]
            d = 100.0 * (m["area_sqft"] - bm["area_sqft"]) / bm["area_sqft"] if bm["area_sqft"] else 0.0
            area_changes.append(abs(d))
            if abs(d) > th["area_pct"]:
                why.append(f"area {d:+.1f}%")
            if abs(m["facets"] - bm["facets"]) > th["facets"]:
                why.append(f"facets {bm['facets']}->{m['facets']}")
            if (bm["fit_all"] or 0) - (m["fit_all"] or 0) > th["fit_all_drop"]:
                why.append(f"fit_all {bm['fit_all']:.2f}->{(m['fit_all'] or 0):.2f}")
            if m["overlap_sqft"] > th["overlap_sqft"] >= bm["overlap_sqft"]:
                why.append("overlap appeared")
        for w in why:
            k = w.split()[0]
            reasons[k] = reasons.get(k, 0) + 1
        if why:
            flagged.append({"id": r["id"], "why": why})
    share = len(flagged) / paired if paired else 0.0
    med = stats.median(area_changes)
    ok = paired > 0 and share <= th["flag_share"] and (med is None or med <= th["median_area_pct"])
    return {"baseline": bdir.name, "n_paired": paired, "n_flagged": len(flagged), "flagged_share": share,
            "median_abs_area_pct": med, "reasons": reasons, "flagged": flagged, "pass": ok, "thresholds": th}
