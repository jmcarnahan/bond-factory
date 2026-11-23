"""Working state of one engine run: the stage products and the context the late stages share."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from .errors import Ctx
from .partition import PartitionRun
from .types import Edge, Facet


@dataclass
class Stages:
    """The intermediate products of one run (building frame), for tests and golden files."""

    theta: float = 0.0
    frame_deg: float = 0.0
    crop: np.ndarray | None = None  # roof points inside footprint + crop buffer (thinned), building frame
    planes: list = field(default_factory=list)  # detected planes (a, b, c arrays), building frame
    plab: np.ndarray | None = None  # plane label per crop point (-1 none)
    outline: Polygon | None = None  # drawn roof edge, building frame
    run: PartitionRun | None = None
    facets: list[Facet] = field(default_factory=list)  # building frame
    edges: list[Edge] = field(default_factory=list)

    def run_summary(self) -> dict[str, Any]:
        """Label-raster summary of the chosen labelling (per label: cells, area, bounding box in cells)."""
        from .types import Partition

        run = self.run
        if run is None:
            return {}
        part = Partition(run.labels, run.origin[0], run.origin[1], run.origin[2], [], run.beta)
        out = part.summary()
        out["planes"] = len(run.planes)
        out["facets"] = len(run.items)
        return out


@dataclass
class Run:
    """Everything the late stages need, in the building frame."""

    ctx: Ctx
    wall: Polygon  # footprint, building frame
    wall_world: Polygon
    pts_all: np.ndarray  # all roof points, building frame
    stages: Stages
    diag: dict[str, Any]
    county: bool
    source: str
    parcel_match: str | None
    context: np.ndarray | None
    ang: float
    timings: dict[str, float]
    jump_pts: np.ndarray | None = None  # building frame; the points level changes are measured from (None: use the plane inliers)

    def tick(self, name: str, t0: float) -> float:
        now = time.perf_counter()
        self.timings[name] = round(now - t0, 3)
        return now
