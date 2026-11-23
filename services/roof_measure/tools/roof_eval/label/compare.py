"""Compare the two independent label runs (r1, r2) of a house and decide whether the label is accepted.

Rule (plan D4, 2026-11-23): a label is ACCEPTED when the two runs agree with each other: their areas differ by at
most 8 % AND their two-sided mean facet IoU (Hungarian matching, an unmatched facet counts 0) is at least 0.6.
The "85 % of in-facet returns within 12 cm" figure is no longer a pass/fail test, it is a confidence tag:
``high`` when BOTH runs reach 85 %, else ``medium``. Anything else is ``rejected_disagree``.

Status values written to labels.tsv: accepted_high, accepted_medium, rejected_disagree, and the bookkeeping states
not_run, running, one_run_only (a label that is waiting for its second run). Nothing is ever deleted except a stale
merged truth file of a house that no longer qualifies.

The merged truth file is the run with the better point fit times coverage, with two keys added:
``confidence`` ("high" or "medium") and ``fit12_pct`` ([r1, r2]).
Houses are opaque ids; the work folder holds houses.tsv (id, folder, optional split and strata), runs/<id>/<tag>/ and
truth/<id>/truth.llm_vision.<tag>.json.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Polygon
from shapely.ops import unary_union

AREA_DIFF_MAX_PCT = 8.0  # accepted when the two areas differ by at most this (inclusive)
FACET_IOU_MIN = 0.6  # accepted when the two-sided facet IoU is at least this (inclusive)
FIT_HIGH_MIN_PCT = 85.0  # both runs at or above this: confidence high
ACCEPTED = ("accepted_high", "accepted_medium")
STATUSES = ACCEPTED + ("rejected_disagree",)
COLS = [
    "id",
    "split",
    "strata",
    "status",
    "confidence",
    "merged_from",
    "area_r1_sqft",
    "area_r2_sqft",
    "area_diff_pct",
    "outline_iou",
    "facet_iou_two_sided",
    "facet_iou_area_weighted",
    "facets_r1",
    "facets_r2",
    "ridge_r1_ft",
    "ridge_r2_ft",
    "hipvalley_r1_ft",
    "hipvalley_r2_ft",
    "fit12_r1_pct",
    "fit12_r2_pct",
    "nofacet_r1_pct",
    "nofacet_r2_pct",
    "flat_r1_sqft",
    "flat_r2_sqft",
    "borderline_r1_sqft",
    "borderline_r2_sqft",
    "conf_r1",
    "conf_r2",
    "cost_r1",
    "cost_r2",
    "why",
    "review_png",
]


def polys(t: dict[str, Any]) -> list[Polygon]:
    return [Polygon(f["polygon"]).buffer(0) for f in t["facets"]]


def iou_matrix(pa: list[Polygon], pb: list[Polygon]) -> np.ndarray:
    m = np.zeros((len(pa), len(pb)))
    for i, p in enumerate(pa):
        for j, q in enumerate(pb):
            if p.intersects(q):
                u = p.union(q).area
                m[i, j] = p.intersection(q).area / u if u > 0 else 0
    return m


def area_diff_pct(a: float, b: float) -> float:
    """100 x |a - b| / mean(a, b); infinite when both are zero-or-less."""
    mean = 0.5 * (a + b)
    return 100.0 * abs(a - b) / mean if mean > 0 else float("inf")


def decide_status(area_pct: float, facet_iou: float, fit_r1: float, fit_r2: float) -> tuple[str, str]:
    """(status, why) from the four numbers; boundaries are inclusive (8.0 % and 0.6 and 85.0 pass)."""
    why = []
    if not area_pct <= AREA_DIFF_MAX_PCT:
        why.append(f"area differs {area_pct:.1f}%")
    if not facet_iou >= FACET_IOU_MIN:
        why.append(f"facet IoU {facet_iou:.3f}")
    if why:
        return "rejected_disagree", "; ".join(why)
    return ("accepted_high" if min(fit_r1, fit_r2) >= FIT_HIGH_MIN_PCT else "accepted_medium"), ""


def metrics(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    pa, pb = polys(a), polys(b)
    ua, ub = unary_union(pa), unary_union(pb)
    m = iou_matrix(pa, pb)
    r, c = linear_sum_assignment(-m)
    matched = m[r, c].sum()
    two = 0.5 * (matched / len(pa) + matched / len(pb))
    wa = sum(p.area * m[i].max() for i, p in enumerate(pa)) / sum(p.area for p in pa)
    wb = sum(q.area * m[:, j].max() for j, q in enumerate(pb)) / sum(q.area for q in pb)

    def hv(t):
        return t["lengths_ft"]["hip"] + t["lengths_ft"]["valley"]

    def fit(t):
        return t["label_check"]["in_facet_within_12cm_pct"] or 0.0

    def nof(t):
        return t["label_check"]["in_no_facet_pct"]

    return {
        "area_r1_sqft": a["area_sqft"],
        "area_r2_sqft": b["area_sqft"],
        "area_diff_pct": area_diff_pct(a["area_sqft"], b["area_sqft"]),
        "outline_iou": ua.intersection(ub).area / ua.union(ub).area,
        "facet_iou_two_sided": two,
        "facet_iou_area_weighted": 0.5 * (wa + wb),
        "facets_r1": a["facet_count"],
        "facets_r2": b["facet_count"],
        "ridge_r1_ft": a["lengths_ft"]["ridge"],
        "ridge_r2_ft": b["lengths_ft"]["ridge"],
        "hipvalley_r1_ft": round(hv(a), 1),
        "hipvalley_r2_ft": round(hv(b), 1),
        "fit12_r1_pct": fit(a),
        "fit12_r2_pct": fit(b),
        "nofacet_r1_pct": nof(a),
        "nofacet_r2_pct": nof(b),
        "flat_r1_sqft": a["flat_area_sqft"],
        "flat_r2_sqft": b["flat_area_sqft"],
        "borderline_r1_sqft": a.get("borderline_area_sqft"),
        "borderline_r2_sqft": b.get("borderline_area_sqft"),
        "conf_r1": a["confidence"],
        "conf_r2": b["confidence"],
        "cost_r1": a["api_run"]["cost_usd"],
        "cost_r2": b["api_run"]["cost_usd"],
    }


def merge(
    a: dict[str, Any], b: dict[str, Any], m: dict[str, Any], confidence: str
) -> tuple[dict[str, Any], str]:
    """The merged truth: the run with the better point fit x coverage, plus confidence and fit12_pct."""
    t = {"r1": a, "r2": b}
    score = {
        k: (t[k]["label_check"]["in_facet_within_12cm_pct"] or 0)
        * (100 - t[k]["label_check"]["in_no_facet_pct"])
        / 100
        for k in t
    }
    best = max(score, key=score.get)
    out = dict(t[best])
    out["labeller_confidence"] = {k: t[k]["confidence"] for k in t}
    out["confidence"] = confidence
    out["fit12_pct"] = [m["fit12_r1_pct"], m["fit12_r2_pct"]]
    out["merged"] = {
        "chosen": best,
        "agreement": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()},
        "rule": f"two runs agree (area <= {AREA_DIFF_MAX_PCT:g} %, two-sided facet IoU >= {FACET_IOU_MIN:g}); "
        f"confidence high when both runs have >= {FIT_HIGH_MIN_PCT:g} % of in-facet returns within 12 cm, else medium; "
        "chosen = better point fit x coverage",
    }
    out.pop("run_tag", None)
    return out, best


def review_png(work: Path, hid: str) -> str:
    from PIL import Image

    rows = []
    for tag in ("r1", "r2"):
        d = work / "runs" / hid / tag
        row = [
            Image.open(d / f"overlay_final_{k}.png").convert("RGB")
            for k in ("aspect", "resid")
            if (d / f"overlay_final_{k}.png").exists()
        ]
        if row:
            rows.append(row)
    if not rows:
        return ""
    w = max(sum(i.width for i in row) for row in rows)
    h = sum(max(i.height for i in row) for row in rows)
    out = Image.new("RGB", (w, h), "white")
    y = 0
    for row in rows:
        x = 0
        for i in row:
            out.paste(i, (x, y))
            x += i.width
        y += max(i.height for i in row)
    p = work / "review" / f"{hid}.png"
    p.parent.mkdir(exist_ok=True)
    out.save(p)
    return str(p)


def decide(work: Path, hid: str) -> dict[str, Any]:
    d = work / "truth" / hid
    t = {}
    for tag in ("r1", "r2"):
        f = d / f"truth.llm_vision.{tag}.json"
        if f.exists():
            t[tag] = json.loads(f.read_text())
    merged = d / "truth.llm_vision.json"
    if len(t) < 2:
        if merged.exists():
            merged.unlink()
        if not t:
            return {"status": "not_run", "why": "no label was produced", "review_png": ""}
        return dict(
            status="one_run_only",
            why=f"only {sorted(t)} produced a label",
            review_png=review_png(work, hid),
            **{f"area_{k}_sqft": v["area_sqft"] for k, v in t.items()},
            **{f"facets_{k}": v["facet_count"] for k, v in t.items()},
            **{f"fit12_{k}_pct": v["label_check"]["in_facet_within_12cm_pct"] for k, v in t.items()},
        )
    m = metrics(t["r1"], t["r2"])
    status, why = decide_status(
        m["area_diff_pct"], m["facet_iou_two_sided"], m["fit12_r1_pct"], m["fit12_r2_pct"]
    )
    shown = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}
    if status in ACCEPTED:
        out, best = merge(t["r1"], t["r2"], m, status.split("_")[1])
        merged.write_text(json.dumps(out, indent=1))
        return dict(
            shown, status=status, confidence=status.split("_")[1], merged_from=best, why="", review_png=""
        )
    if merged.exists():
        merged.unlink()
    return dict(
        shown, status=status, confidence="", merged_from="", why=why, review_png=review_png(work, hid)
    )


def read_houses(work: Path) -> list[dict[str, str]]:
    with open(work / "houses.tsv") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def rebuild(work: Path) -> list[dict[str, Any]]:
    """Decide every house in houses.tsv and rewrite labels.tsv."""
    rows = []
    for h in read_houses(work):
        base = {"id": h["id"], "split": h.get("split", ""), "strata": h.get("strata", "")}
        if not (work / "truth" / h["id"]).exists() and not (work / "runs" / h["id"]).exists():
            rows.append(dict(base, status="not_run", why="queue not reached"))
        elif not all((work / "runs" / h["id"] / tag / "run.json").exists() for tag in ("r1", "r2")):
            rows.append(dict(base, status="running"))
        else:
            rows.append(dict(base, **decide(work, h["id"])))
    with open(work / "labels.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return rows
