"""The plane engine reached through the pipeline gives the same roof as the harness CLI on the same house.

A synthetic house is written in the exact convention of the regression set (``points_wide.npy`` in a local metric frame
with absolute z, ``footprint.json``, ``meta.json``, and the ``points.npy`` the research cut with reach
min(0.6 m, 8% of the side)). ``measure(points_path=...)`` is the offline entry of the engine path. This class of bug once
shipped: the pipeline cut the roof points with a 1.3 m reach, pulled trees and the neighbour's wall into the planes and
measured a pitched roof as half flat."""

from __future__ import annotations

import json

import numpy as np
import pytest
from engine_cases import case

from roof_measure import library, pipeline_engine
from roof_measure.engine import measure_roof
from roof_measure.engine.load import load_house
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
    d.mkdir()
    np.save(d / "points_wide.npy", wide.astype(np.float32))
    rp = roof_points(wide, wall, overhang_m=min(0.6, 0.08 * wall.area ** 0.5), min_height_m=1.5)
    np.save(d / "points.npy", rp.xyz.astype(np.float32))
    (d / "footprint.json").write_text(json.dumps({"polygon": [list(p) for p in wall.exterior.coords]}))
    (d / "meta.json").write_text(json.dumps({"frame": {"crs_epsg": 32611, "x0_m": X0, "y0_m": Y0}, "outline_source": "lariac",
                                             "parcel_match": "exact", "lidar": {"project": "SYNTHETIC", "year": 2023}}))
    return d


def summary(totals, quality, facets):
    return {"facets": len(facets), "area": totals["planes_surface_area_sqft"], "ridge_hip": totals["ridge_cap_ridge_hip_ft"],
            "perimeter": totals["outline_perimeter_ft"], "pitched": totals["roofing_pitched_sqft"], "flat": totals["roofing_flat_sqft"],
            "fit_all": quality["fit_all"]}


@pytest.mark.parametrize("name", ["gable_d8", "hip_d8", "l_shape_d8", "flat_pitched_d8"])
def test_the_pipeline_engine_path_equals_the_harness_cli_on_the_same_house(tmp_path, name):
    d = write_house(tmp_path, name)
    h = load_house(d)
    cli = measure_roof(h.points, h.footprint, outline_source=str(h.meta["outline_source"]), parcel_match=h.meta["parcel_match"],
                       context=h.wide)
    env = library.measure("", engine="planes", points_path=d, cache_dir=tmp_path / "c", isolate=False, verify=False)
    m = env["model"]
    want = summary(cli.totals, cli.quality.to_dict(), cli.facets)
    got = summary(env["totals"], m["quality"], m["facets"])
    assert got["facets"] == want["facets"]
    for k in ("area", "pitched", "flat", "ridge_hip", "perimeter"):
        assert got[k] == pytest.approx(want[k], rel=0.02, abs=2.0), k
    assert got["fit_all"] == pytest.approx(want["fit_all"], abs=0.02)
    assert m["quality"]["engine"] == "planes/1" and m["quality"]["outline_source"] == "lacounty_lariac_2020"
    assert m["quality"]["overhang_scale"] == 0.5 and m["quality"]["parcel_match"] == "exact"


def test_the_pipeline_cuts_the_roof_points_like_the_regression_data(tmp_path, monkeypatch):
    d = write_house(tmp_path)
    seen = []
    import roof_measure.engine as engine_pkg

    real = engine_pkg.measure_roof
    monkeypatch.setattr(engine_pkg, "measure_roof", lambda points, *a, **k: seen.append(np.asarray(points.xyz)) or real(points, *a, **k))
    library.measure("", engine="planes", points_path=d, cache_dir=tmp_path / "c", isolate=False, verify=False)
    stored = np.load(d / "points.npy").astype(float)
    got = seen[0]
    # the same points, except for float32 storage and the frame shift: compare rounded to 1 cm
    key = lambda a: {tuple(r) for r in np.round(a[:, :3], 2)}
    assert len(got) == len(stored) and len(key(got) ^ key(stored)) <= 0.01 * len(stored)


def test_the_old_1_3_m_reach_would_fail_the_two_tests_above(tmp_path, monkeypatch):
    """The guard guards: with the earlier reach the point set differs from the regression data."""
    monkeypatch.setattr(pipeline_engine, "MAX_OVERHANG_M", 1.3)
    d = write_house(tmp_path)
    seen = []
    import roof_measure.engine as engine_pkg

    real = engine_pkg.measure_roof
    monkeypatch.setattr(engine_pkg, "measure_roof", lambda points, *a, **k: seen.append(len(points.xyz)) or real(points, *a, **k))
    library.measure("", engine="planes", points_path=d, cache_dir=tmp_path / "c", isolate=False, verify=False)
    assert seen[0] > len(np.load(d / "points.npy")) * 1.05


def test_the_offline_entry_validates_its_arguments(tmp_path):
    d = write_house(tmp_path)
    kw = {"cache_dir": tmp_path / "c", "isolate": False}
    with pytest.raises(ValueError, match="points_path needs engine"):
        library.measure("", points_path=d, **kw)
    with pytest.raises(ValueError, match="house folder"):
        library.measure("", engine="planes", points_path=tmp_path, **kw)
    with pytest.raises(ValueError, match="address must not be blank"):
        library.measure("", engine="planes", **kw)
    assert pipeline_engine.MAX_OVERHANG_M == 0.6  # restored after the monkeypatched test
