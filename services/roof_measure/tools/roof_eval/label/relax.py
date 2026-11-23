"""Relaxed fit report: re-check each run's final label against the LiDAR with a looser tolerance on flat facets.

Since plan D4 the "85 % of in-facet returns within 12 cm" figure is a confidence tag, not a pass/fail test, so this
report never changes a status. It adds columns fit_r1_relaxed, fit_r2_relaxed and confidence_relaxed (high when both
runs reach 85 % with the flat-facet tolerance below, else medium) to labels.tsv for accepted houses, so a person can see
how many ``medium`` labels are medium only because flat roofs carry drainage falls and equipment.
Usage: python -m tools.roof_eval.label relax --work-dir DIR   (the original columns are never changed)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from shapely import contains_xy
from shapely.ops import unary_union

from . import build as lt
from . import viz as rv
from .compare import ACCEPTED, FIT_HIGH_MIN_PCT, read_houses

FLAT_TOL_M = 0.20  # tolerance on facets flatter than 2/12; every other facet keeps 12 cm
BASE_TOL_M = 0.12


def fit(h: rv.House, label: dict[str, Any], tol_flat: float) -> float:
    """Share (%) of roof returns near the label that lie within tolerance of their own facet's plane."""
    _, facets, _, polys = lt.build(h, label, "llm_vision", "")
    union = unary_union([p.buffer(0) for p in polys.values()])
    zone = union.buffer(1.0).union(h.fp.buffer(0.5))
    p = h.ng[h.ng_hag > 1.8]
    p = p[contains_xy(zone, p[:, 0], p[:, 1])]
    res = np.full(len(p), np.nan)
    tol = np.full(len(p), BASE_TOL_M)
    for f in facets:
        if not f["plane"]:
            continue
        m = contains_xy(polys[f["id"]], p[:, 0], p[:, 1])
        res[m] = p[m, 2] - lt._z(f["plane"], p[m, 0], p[m, 1])
        if f["pitch_rise"] is not None and f["pitch_rise"] < 2.0:
            tol[m] = tol_flat
    ok = ~np.isnan(res)
    return round(100 * float((np.abs(res[ok]) < tol[ok]).mean()), 1)


def final_label(work: Path, hid: str, tag: str) -> dict[str, Any] | None:
    subs = sorted((work / "runs" / hid / tag).glob("label_submit*.json"))
    return json.loads(subs[-1].read_text()) if subs else None


def main(work: Path) -> list[tuple[str, str, str]]:
    with open(work / "labels.tsv") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    cols = list(rows[0].keys()) if rows else []
    for c in ("fit_r1_relaxed", "fit_r2_relaxed", "confidence_relaxed"):
        if c not in cols:
            cols.append(c)
    folders = {h["id"]: h["folder"] for h in read_houses(work)}
    changed = []
    for r in rows:
        if r["status"] not in ACCEPTED:
            continue
        house = rv.House(folders[r["id"]])
        fr = {}
        for tag in ("r1", "r2"):
            fr[tag] = fit(house, final_label(work, r["id"], tag), FLAT_TOL_M)
            r[f"fit_{tag}_relaxed"] = fr[tag]
            if (
                abs(fit(house, final_label(work, r["id"], tag), BASE_TOL_M) - float(r[f"fit12_{tag}_pct"]))
                > 0.3
            ):
                print("WARN: stored 12 cm fit not reproduced for", r["id"], tag)
        r["confidence_relaxed"] = "high" if min(fr.values()) >= FIT_HIGH_MIN_PCT else "medium"
        if r["confidence_relaxed"] != r.get("confidence"):
            changed.append((r["id"], r.get("confidence", ""), r["confidence_relaxed"]))
    with open(work / "labels.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return changed
