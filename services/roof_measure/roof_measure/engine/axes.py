"""The building frame: dominant wall direction, rotating clouds and results in and out of it. Metres, degrees."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from shapely import affinity
from shapely.geometry import Polygon

from .plane_math import PlaneLike


def dominant_axis(poly: Polygon) -> float:
    """Dominant edge direction of the polygon's exterior, degrees modulo 90, length weighted (circular mean)."""
    c = np.array(poly.exterior.coords)
    d = np.diff(c, axis=0)
    length = np.hypot(d[:, 0], d[:, 1])
    a = np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 90.0
    z = (length * np.exp(1j * np.radians(a) * 4)).sum()
    return (np.degrees(np.angle(z)) / 4.0) % 90.0


def to_building_frame(xy: np.ndarray, ang: float) -> np.ndarray:
    """Rotate world (n, 2) coordinates by ``-ang`` degrees (the wall axis becomes +x)."""
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return np.c_[xy[:, 0] * c + xy[:, 1] * s, -xy[:, 0] * s + xy[:, 1] * c]


def rotate_plane(plane: PlaneLike, ang: float) -> np.ndarray:
    """A plane given in the building frame, expressed in the world frame (gradient rotated by ``ang`` degrees)."""
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return np.array([plane[0] * c - plane[1] * s, plane[0] * s + plane[1] * c, plane[2]])


def poly_to_world(poly: Polygon, ang: float) -> Polygon:
    """Rotate a building-frame polygon back to the world frame."""
    return affinity.rotate(poly, ang, origin=(0, 0))


def point_to_world(pt: Sequence[float], ang: float) -> list[float]:
    """Rotate an edge end ``[x, y, z]`` back to the world frame (z unchanged)."""
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [float(pt[0] * c - pt[1] * s), float(pt[0] * s + pt[1] * c), pt[2]]
