"""Plane arithmetic. A plane is ``z = a*x + b*y + c`` stored as an array ``(a, b, c)``; x, y, z in metres."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

PlaneLike = np.ndarray | Sequence[float]  # (a, b, c) or anything indexable like it


def fit_plane(pts: np.ndarray) -> np.ndarray:
    """Least-squares plane through (n, 3) points: ``(a, b, c)``."""
    design = np.c_[pts[:, 0], pts[:, 1], np.ones(len(pts))]
    sol, *_ = np.linalg.lstsq(design, pts[:, 2], rcond=None)
    return sol


def pres(plane: PlaneLike, pts: np.ndarray) -> np.ndarray:
    """Signed vertical residual ``z - plane(x, y)`` in metres."""
    return pts[:, 2] - (plane[0] * pts[:, 0] + plane[1] * pts[:, 1] + plane[2])


def pdist(plane: PlaneLike, pts: np.ndarray) -> np.ndarray:
    """Perpendicular distance of each point to the plane, metres."""
    return np.abs(pres(plane, pts)) / math.sqrt(1 + plane[0] ** 2 + plane[1] ** 2)


def zat(plane: PlaneLike, x: float | np.ndarray, y: float | np.ndarray) -> float | np.ndarray:
    """Plane height at (x, y), metres."""
    return plane[0] * x + plane[1] * y + plane[2]


def aspect_deg(plane: PlaneLike) -> float:
    """Downslope compass azimuth in degrees (0 = north, 90 = east)."""
    return math.degrees(math.atan2(-plane[0], -plane[1])) % 360.0


def pitch_rise(plane: PlaneLike) -> float:
    """Pitch as rise per 12 of run (2.0 is a 2/12 pitch)."""
    return 12.0 * math.hypot(plane[0], plane[1])


def compact(lab: np.ndarray, planes: list) -> tuple[np.ndarray, list]:
    """Drop planes without members and renumber the labels (``-1`` stays unassigned)."""
    keep = [i for i in range(len(planes)) if (lab == i).sum() > 0]
    remap = {o: n for n, o in enumerate(keep)}
    lab2 = np.array([remap.get(v, -1) if v >= 0 else -1 for v in lab], dtype=int)
    return lab2, [planes[i] for i in keep]
