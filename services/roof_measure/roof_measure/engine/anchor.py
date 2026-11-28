"""The one anchor every grid, voxel and bin of the engine hangs on: the median of the roof points.

A lattice anchored on the frame origin, the footprint or the crop's corner moves when the footprint is nudged (the frame is
cut from the footprint's south-west corner; the crop's fringe follows the footprint) and with it every threshold decision
made on the lattice. The median of a few thousand returns moves by centimetres at most when a few edge returns come or go,
and moves exactly with the points under a translation."""

from __future__ import annotations

import numpy as np


def anchor_of(xy: np.ndarray) -> np.ndarray:
    """Median x, y of ``xy`` (n, >= 2); (0, 0) for no points."""
    return np.median(xy[:, :2], axis=0) if len(xy) else np.zeros(2)
