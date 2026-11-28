"""Helpers of test_engine_improve*.py: the engine on the extra synthetic roofs (synth_extra) and on the standard ones.

The totals are those of the drawn roof, the full roof edge, which is what the synthetic truth is."""

from __future__ import annotations

from functools import cache

from roof_measure.engine import measure_roof, synth_extra, synth_points
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.params import DEFAULT, EngineParams


@cache
def cases() -> dict:
    return synth_extra.with_extra({c.name: c for c in synth_points.cases()})


@cache
def run(name: str, params: EngineParams = DEFAULT):
    """Engine result for case ``name`` (cached: the engine is deterministic)."""
    c = cases()[name]
    pts = c.points()
    wall = c.roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    return measure_roof(rp, wall, params=params, outline_source="county", parcel_match="given", context=pts)


def truth(name: str):
    from tools.roof_eval import synth  # the exact roof, shifted back for an outline-offset case

    return synth.exact_roof(cases()[name])


def drawn_area(res) -> float:
    return sum(f.area_sqft for f in res.facets)


def length(res, kind: str) -> float:
    return sum(e.length_ft for e in res.edges if e.type == kind)


def measure_roof_for(roof, density: int, extra=None, params: EngineParams = DEFAULT, seed: int = 1):
    """Engine result for any SynthRoof; ``extra(roof)`` may add returns (an (n, 4) array: x, y, z, class)."""
    import numpy as np

    from roof_measure.engine import synth_points

    pts = synth_points.simulate(roof, density=density, seed=seed)
    if extra is not None:
        pts = np.vstack([pts, extra(roof)])
    wall = roof.wall_polygon()
    rp = roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts)
    return measure_roof(rp, wall, params=params, outline_source="county", parcel_match="given", context=pts)
