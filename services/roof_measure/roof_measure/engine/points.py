"""Roof point selection: which LiDAR returns belong to the roof of one building.

The numbers are pinned by ``tests/test_engine_points.py``.

A return is a roof point when it is not ground (class 2) and stands more than ``min_height_m`` above the LOCAL ground
(the median of the 8 nearest class-2 returns; the site ground when there is none) and lies within ``overhang_m`` of
the footprint. Points a plane-fit radius further out are kept in ``xyz`` too (they feed the per-cell plane fits of
cells at the edge) but are not counted on the roof. Metres, any metric frame (``footprint_m`` in the same frame).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import Polygon

PLANE_RADIUS_M = 0.6  # neighbourhood for the per-cell plane fit: ``xyz`` reaches this far past the overhang


@dataclass
class RoofPoints:
    """The roof's returns and the numbers every later stage quotes."""

    xyz: np.ndarray  # (n, 3) roof returns within overhang + plane radius of the footprint (what plane fits read)
    ground_z: float  # site ground height: median of the class-2 returns in an 8 m ring round the footprint
    ground_xyz: np.ndarray  # (m, 3) the class-2 returns
    n_on_roof: int  # roof returns within the overhang reach (the envelope's ``points_on_roof``)
    n_inside: int  # roof returns strictly inside the footprint
    density: float  # n_inside per m2 of footprint: the roof density every refusal and warning uses
    on_roof: np.ndarray  # (n,) bool over the INPUT points: the returns counted in ``n_on_roof``

    def __len__(self) -> int:
        return len(self.xyz)


def local_ground(ground_tree: cKDTree | None, ground_z: np.ndarray, xy: np.ndarray, fallback: float) -> np.ndarray:
    """Median z of the 8 nearest class-2 points; the fallback when there is no ground at all."""
    if ground_tree is None:
        return np.full(len(xy), fallback)
    k = min(8, len(ground_z))
    _, ii = ground_tree.query(xy, k=k)
    return np.median(ground_z[np.atleast_2d(ii.reshape(len(xy), -1))], axis=1)


def roof_points(points_xyzc: np.ndarray, footprint_m: Polygon, *, overhang_m: float, min_height_m: float,
                plane_radius_m: float = PLANE_RADIUS_M) -> RoofPoints:
    """Select the roof returns of one building.

    ``points_xyzc`` is an (n, 4) array of x, y, z and the ASPRS class; ``footprint_m`` the building outline in the same
    metric frame; ``overhang_m`` how far the roof may reach past it; ``min_height_m`` the height above local ground
    below which a return is a car, a bush or the ground itself.
    """
    pts = np.asarray(points_xyzc, dtype=float).reshape(-1, 4)
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    is_ground = pts[:, 3] == 2
    g_xy = np.column_stack([x[is_ground], y[is_ground]])
    g_z = z[is_ground]
    gtree = cKDTree(g_xy) if len(g_xy) >= 3 else None
    ring = (contains_xy(footprint_m.buffer(8.0), x[is_ground], y[is_ground])
            & ~contains_xy(footprint_m.buffer(0.5), x[is_ground], y[is_ground]))
    ground_z = float(np.median(g_z[ring])) if ring.any() else float(np.median(g_z) if len(g_z) else np.percentile(z, 2))
    reach = footprint_m.buffer(overhang_m)
    near = contains_xy(footprint_m.buffer(overhang_m + plane_radius_m), x, y)
    hag = np.full(len(z), np.nan)
    if near.any():
        hag[near] = z[near] - local_ground(gtree, g_z, np.column_stack([x[near], y[near]]), ground_z)
    tall = ~is_ground & (hag > min_height_m)  # a nan height compares False
    sel = near & tall
    inside = int((contains_xy(footprint_m, x, y) & tall).sum())
    area = footprint_m.area
    on_roof = contains_xy(reach, x, y) & tall
    return RoofPoints(xyz=np.column_stack([x[sel], y[sel], z[sel]]), ground_z=ground_z,
                      ground_xyz=np.column_stack([g_xy, g_z]), n_on_roof=int(on_roof.sum()), n_inside=inside,
                      density=inside / area if area else 0.0, on_roof=on_roof)
