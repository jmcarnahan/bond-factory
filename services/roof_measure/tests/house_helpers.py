"""A synthetic house folder in the regression set's convention: the offline entry (``measure(points_path=...)``) of the
plane engine for tests. Synthetic roofs only."""

from __future__ import annotations

import json

import numpy as np
from engine_cases import case

from roof_measure.engine.points import roof_points

X0, Y0 = 500000.0, 4000000.0  # an invented grid origin


def write_house(path, name="gable_d8", clutter=True):
    c = case(name)
    wall = c.roof.wall_polygon()
    wide = c.points().copy()
    if clutter:  # a tall wall 1.22-1.29 m outside the footprint: not roof; a 0.6 m reach (plus the 0.6 m plane radius) leaves it out, a 1.3 m reach keeps it
        rng = np.random.default_rng(1)
        minx, _miny, maxx, maxy = wall.bounds
        n = 250
        ring = np.c_[rng.uniform(minx, maxx, n), np.full(n, maxy + rng.uniform(1.22, 1.29, n)), rng.uniform(5.5, 9.0, n), np.ones(n)]
        wide = np.vstack([wide, ring])
    d = path / "h-synthetic"
    d.mkdir(parents=True)
    np.save(d / "points_wide.npy", wide.astype(np.float32))
    rp = roof_points(wide, wall, overhang_m=min(0.6, 0.08 * wall.area ** 0.5), min_height_m=1.5)
    np.save(d / "points.npy", rp.xyz.astype(np.float32))
    (d / "footprint.json").write_text(json.dumps({"polygon": [list(p) for p in wall.exterior.coords]}))
    (d / "meta.json").write_text(json.dumps({"frame": {"crs_epsg": 32611, "x0_m": X0, "y0_m": Y0}, "outline_source": "lariac",
                                             "parcel_match": "exact", "lidar": {"project": "SYNTHETIC", "year": 2023}}))
    return d


def house(tmp_path, name="gable_d8"):
    """``write_house`` once per (folder, case): the same call twice returns the same house."""
    d = tmp_path / f"houses-{name}"
    return d / "h-synthetic" if d.exists() else write_house(d, name)
