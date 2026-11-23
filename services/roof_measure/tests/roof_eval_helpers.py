"""Hand-built synthetic roofs for the roof_eval tests (metres, local frame). No real data anywhere."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

W, D = 12.0, 8.0  # roof plan size, metres
EAVE, RISE = 3.0, 0.5  # eave height, slope (6/12)
FT = 1 / 0.3048


def rect(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def facet(fid, poly, plane, pitch=None, roof_type=None):
    pitch = 12 * math.hypot(plane[0], plane[1]) if pitch is None else pitch
    return {"id": fid, "polygon": poly, "plane": list(plane), "pitch_rise": pitch,
            "roof_type": roof_type or ("flat" if pitch < 2 else "pitched")}


def edge(t, p0, p1, facets):
    return {"type": t, "p0": list(p0), "p1": list(p1), "length_ft": math.dist(p0, p1) * FT, "facets": facets}


def gable_result():
    """A 12 x 8 m gable, ridge along x at y = 4, 6/12: two facets, two eaves, two rakes, one ridge."""
    zr = EAVE + RISE * 4
    fs = [facet("f1", rect(0, 0, W, 4), (0, RISE, EAVE)), facet("f2", rect(0, 4, W, D), (0, -RISE, EAVE + RISE * D))]
    es = [edge("eave", (0, 0, EAVE), (W, 0, EAVE), ["f1"]), edge("eave", (0, D, EAVE), (W, D, EAVE), ["f2"]),
          edge("rake", (0, 0, EAVE), (0, 4, zr), ["f1"]), edge("rake", (W, 0, EAVE), (W, 4, zr), ["f1"]),
          edge("rake", (0, D, EAVE), (0, 4, zr), ["f2"]), edge("rake", (W, D, EAVE), (W, 4, zr), ["f2"]),
          edge("ridge", (0, 4, zr), (W, 4, zr), ["f1", "f2"])]
    return {"slug": "synthetic", "facets": fs, "edges": es, "roof_outline": rect(0, 0, W, D),
            "diagnostics": {"quality": {"verdict": "ok"}}, "totals": {}}


def gable_points(step=0.5, noise=0.0, seed=1):
    xs = np.arange(step / 2, W, step)
    ys = np.arange(step / 2, D, step)
    X, Y = np.meshgrid(xs, ys)
    Z = EAVE + RISE * np.minimum(Y, D - Y)
    pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    if noise:
        pts[:, 2] += np.random.default_rng(seed).normal(0, noise, len(pts))
    return pts


def footprint():
    return np.array(rect(0.5, 0.5, W - 0.5, D - 0.5))


def truth_for(result, **extra):
    t = {"source": "llm_vision", "confidence": "medium", "facets": [
        {"polygon": f["polygon"], "pitch_rise": f["pitch_rise"], "roof_type": f["roof_type"]} for f in result["facets"]]}
    t.update(extra)
    return t


# ---- deliberately wrong results ----
def one_big_facet(res):
    r = copy.deepcopy(res)
    r["facets"] = [facet("f1", rect(0, 0, W, D), (0, 0, EAVE + RISE * 2))]
    r["edges"] = [e for e in r["edges"] if e["type"] in ("eave", "rake")]
    return r


def shrunk(res, m=1.5):
    r = copy.deepcopy(res)
    for f in r["facets"]:
        ring = Polygon(f["polygon"]).buffer(-m, join_style="mitre").exterior.coords
        f["polygon"] = [list(c) for c in ring][:-1]
    return r


def split_four(res):
    r = copy.deepcopy(res)
    out = []
    for f in r["facets"]:
        xs = [c[0] for c in f["polygon"]]
        ys = [c[1] for c in f["polygon"]]
        mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        for k, (a, b, c, d) in enumerate([(min(xs), min(ys), mx, my), (mx, min(ys), max(xs), my),
                                          (min(xs), my, mx, max(ys)), (mx, my, max(xs), max(ys))]):
            out.append({**f, "id": f"{f['id']}_{k}", "polygon": rect(a, b, c, d)})
    r["facets"] = out
    return r


def ridge_shifted(res, dy=1.0):
    r = copy.deepcopy(res)
    ys = 4 + dy
    r["facets"] = [facet("f1", rect(0, 0, W, ys), (0, (RISE * 4) / ys, EAVE)),
                   facet("f2", rect(0, ys, W, D), (0, -(RISE * 4) / (D - ys), EAVE + RISE * 4 + RISE * 4 / (D - ys) * ys))]
    return r


def with_level_change(res, x=6.0):
    """A level_change edge placed across a continuous roof surface: the points show no jump there."""
    r = copy.deepcopy(res)
    r["edges"].append(edge("level_change", (x, 0.5, 3.25), (x, 3.5, 4.75), ["f1"]))
    return r


def overlapping(res):
    r = copy.deepcopy(res)
    r["facets"].append(facet("f3", rect(2, 1, 8, 3), (0, RISE, EAVE)))
    return r


def all_flat(res):
    r = copy.deepcopy(res)
    for f in r["facets"]:
        f["plane"] = [0.0, 0.0, EAVE + RISE * 2]
        f["pitch_rise"], f["roof_type"] = 0.0, "flat"
    return r


def two_level_points(jump=1.0):
    """Two flat decks 1 m apart meeting at x = 6 (true level change)."""
    xs, ys = np.arange(0.25, W, 0.5), np.arange(0.25, D, 0.5)
    X, Y = np.meshgrid(xs, ys)
    Z = np.where(X < 6, 3.0, 3.0 + jump)
    return np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)


# ---- a tiny data root for the runner tests ----
def build_root(root: Path, n=4, with_truth=True):
    """manifest + houses + truth for ``n`` synthetic gables (ids h-0000000k); returns the list of ids."""
    rows, ids = [], []
    for k in range(n):
        hid = f"h-{k:08x}"
        ids.append(hid)
        hd = root / "houses" / hid
        hd.mkdir(parents=True)
        pts = gable_points(noise=0.01, seed=k)
        ground = np.array([[x, y, 0.0, 2.0] for x in np.arange(-6, W + 6, 1.5) for y in np.arange(-6, D + 6, 1.5)
                           if not (0 <= x <= W and 0 <= y <= D)])
        wide = np.vstack([np.c_[pts, np.ones(len(pts))], ground])
        np.save(hd / "points.npy", pts.astype(np.float32))
        np.save(hd / "points_wide.npy", wide.astype(np.float32))
        (hd / "footprint.json").write_text(json.dumps({"polygon": footprint().tolist()}))
        (hd / "meta.json").write_text(json.dumps({"parcel_match": "exact", "density": 4.0, "outline_source": "county"}))
        res = gable_result()
        if with_truth:
            td = root / "truth" / hid
            td.mkdir(parents=True)
            sq = 960.0 / 100
            (td / "truth.llm_vision.json").write_text(json.dumps(truth_for(res, squares=sq, predominant_pitch=6.0)))
            (td / "truth.contractor_squares.json").write_text(json.dumps(
                {"source": "contractor_squares", "confidence": "medium", "squares": 10.0}))
        rows.append({"id": hid, "split": "tuning" if k < n - 1 else "negative", "roof_class": "pitched",
                     "complexity": "simple", "region": "LA", "density_band": "4-8", "flags": [],
                     "facet_count_ref": 2, "facet_count_src": "vision_label", "density_pts_m2": 8.0, "parcel_match": "exact", "tiers": ["T2", "T3"]})
    (root / "manifest.json").write_text(json.dumps(rows))
    return ids
