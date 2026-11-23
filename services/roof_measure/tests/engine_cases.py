"""Shared helpers of the engine tests: run the engine on a synthetic roof (the only data in this repo)."""

from __future__ import annotations

from functools import cache

from roof_measure.engine import measure_roof, synth_points
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.engine.params import DEFAULT, EngineParams


@cache
def _cases() -> dict:
    return {c.name: c for c in synth_points.cases()}


def case(name: str):
    return _cases()[name]


def inputs(name: str):
    """(RoofPoints, wall polygon, full cloud) of synthetic case ``name``."""
    c = case(name)
    pts = c.points()
    wall = c.roof.wall_polygon()
    return roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts), wall, pts


@cache
def run(name: str, params: EngineParams = DEFAULT):
    """The engine result for synthetic case ``name`` (cached: the engine is deterministic)."""
    rp, wall, pts = inputs(name)
    return measure_roof(rp, wall, params=params, outline_source="county", parcel_match="given", context=pts)
