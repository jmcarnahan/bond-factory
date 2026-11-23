"""A stub engine for the roof_eval runner tests: ``python roof_eval_stub_engine.py MODE <house_dir> <out_json>``."""

import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import roof_eval_helpers as H

mode, hdir, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
res = H.gable_result()
if mode == "bigfacet":
    res = H.one_big_facet(res)
elif mode == "refuse":
    res = {"facets": [], "edges": [], "roof_outline": [], "diagnostics": {"quality": {"verdict": "refused"}}}
elif mode in ("sparse", "lowdensity"):
    res = {"facets": [], "edges": [], "roof_outline": [],
           "diagnostics": {"quality": {"verdict": "lidar_too_sparse" if mode == "sparse" else "low_density"}}}
elif mode in ("peek", "listing"):  # an engine must not see anything but the sanitised inputs
    if mode == "peek":
        np.load(hdir / "reference_points.npy")  # FileNotFoundError: the engine fails
        for name in ("envelope.json",):
            (hdir / name).read_text()
    res["diagnostics"]["listing"] = sorted(p.name for p in hdir.iterdir())
    res["diagnostics"]["meta"] = json.loads((hdir / "meta.json").read_text())
    res["diagnostics"]["parent"] = sorted(p.name for p in hdir.parent.iterdir())
elif mode == "onefacet_big":  # one facet padded 4 m beyond the roof: no points under the padding
    res["facets"] = [H.facet("f1", H.rect(-4, -4, H.W + 4, H.D + 4), (0, 0, 5.0))]
    res["edges"] = []
elif mode == "split2":  # every facet cut in two coplanar halves (over-segmentation)
    pieces = []
    for f in res["facets"]:
        xs = [c[0] for c in f["polygon"]]
        ys = [c[1] for c in f["polygon"]]
        mx = (min(xs) + max(xs)) / 2
        pieces += [{**f, "id": f["id"] + "a", "polygon": H.rect(min(xs), min(ys), mx, max(ys))},
                {**f, "id": f["id"] + "b", "polygon": H.rect(mx, min(ys), max(xs), max(ys))}]
    res["facets"] = pieces
elif mode == "cells":  # 2 m cells, each with its own least-squares plane (the adversary's quadtree)
    w = np.load(hdir / "points_wide.npy").astype(float)
    p = w[(w[:, 3] != 2) & (w[:, 2] > 1.5)]
    fs = []
    for x in np.arange(0, H.W, 2.0):
        for y in np.arange(0, H.D, 2.0):
            q = p[(p[:, 0] >= x) & (p[:, 0] < x + 2) & (p[:, 1] >= y) & (p[:, 1] < y + 2)]
            if len(q) >= 6:
                a, b, c = np.linalg.lstsq(np.c_[q[:, 0], q[:, 1], np.ones(len(q))], q[:, 2], rcond=None)[0]
                fs.append(H.facet(f"c{len(fs)}", H.rect(x, y, x + 2, y + 2), (a, b, c)))
    res["facets"], res["edges"] = fs, []
elif mode == "unmarked":  # two decks 1 m apart; the boundary is not typed level_change
    res["facets"] = [H.facet("l", H.rect(0, 0, 6, H.D), (0, 0, 3.0)), H.facet("r", H.rect(6, 0, H.W, H.D), (0, 0, 4.0))]
    res["edges"] = []
elif mode in ("badjson", "list", "empty_obj", "nan_plane", "inf_plane", "no_plane", "str_facets", "facets_not_list", "verdict_list",
              "nan_poly", "huge"):
    good = {"facets": [{"id": "f1", "polygon": H.rect(0, 0, 4, 4), "plane": [0, 0, 5.0]}], "edges": [],
            "diagnostics": {"quality": {"verdict": "ok"}}}
    if mode == "badjson":
        out.write_text('{"facets": [')
        sys.exit(0)
    if mode == "list":
        out.write_text("[1,2,3]")
        sys.exit(0)
    if mode == "empty_obj":
        good = {}
    elif mode == "nan_plane":
        good["facets"][0]["plane"] = [float("nan")] * 3
    elif mode == "inf_plane":
        good["facets"][0]["plane"] = [float("inf"), 0, 0]
    elif mode == "no_plane":
        del good["facets"][0]["plane"]
    elif mode == "str_facets":
        good["facets"] = ["a", "b"]
    elif mode == "facets_not_list":
        good["facets"] = {"x": 1}
    elif mode == "verdict_list":
        good["diagnostics"]["quality"]["verdict"] = ["ok"]
    elif mode == "nan_poly":
        good["facets"][0]["polygon"] = [[float("nan"), 0], [1, 0], [1, 1]]
    elif mode == "huge":
        good["facets"][0]["polygon"] = H.rect(-1e6, -1e6, 1e6, 1e6)
    res = good
elif mode == "overlap":
    res = H.overlapping(res)
elif mode == "flatswap":
    res = H.all_flat(res)
elif mode == "poor":
    res["diagnostics"]["quality"]["verdict"] = "poor_fit"
elif mode == "crash":
    print("boom: engine exploded", file=sys.stderr)
    sys.exit(1)
elif mode == "slow":
    time.sleep(30)
elif mode == "random":  # a non-deterministic engine
    res["facets"][0]["plane"][2] += random.random() * 0.01
out.write_text(json.dumps(res))
