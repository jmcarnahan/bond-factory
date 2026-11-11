"""LiDAR hull link of the footprint chain (plan D6): the last resort when no map source has the building.

The outline is the closed boundary of the roof-height connected component nearest the point. Guards: vegetation
classes are dropped, rough components (trees) are rejected, two comparable buildings close together raise
``AmbiguousBuilding``, and the hull area is cross-checked against the cells it came from.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from scipy import ndimage
from shapely import union_all
from shapely.geometry import Point, Polygon, box
from shapely.geometry.polygon import orient

from . import lidar
from .deadline import Deadline
from .footprint_types import AmbiguousBuilding, Footprint, FootprintError, FootprintUnavailable, area_sqft
from .frame import FT_PER_M, project_geometry, utm_epsg_for

log = logging.getLogger(__name__)

CELL_M = 1.0
SEARCH_HALF_M = 45.0
MIN_ROOF_HEIGHT_M = 2.5  # above local ground
MAX_ROOF_HEIGHT_M = 40.0
MIN_COMPONENT_M2 = 25.0
MAX_POINT_DIST_M = 35.0  # the chosen component must lie this close to the point
ROUGH_RANGE_M = 1.2  # a 3x3 height range (roof cells only) above this marks a cell rough
MAX_ROUGH_SHARE = 0.45
AMBIGUOUS_RATIO = 0.5
AMBIGUOUS_GAP_M = 10.0
MAX_AREA_RATIO = 1.5
DROP_CLASSES = (2, 3, 4, 5, 7, 9, 18)  # ground, vegetation, noise, water
HULL_NOTE = "Footprint derived from the LiDAR point cloud only; check that the outline is the right building."
VEGETATION = (3, 4, 5)


@dataclass
class Component:
    mask: np.ndarray  # bool grid
    polygon: Polygon  # metres, local to the grid origin
    area_m2: float
    rough_share: float
    height_m: float


def ground_level(z: np.ndarray, cls: np.ndarray) -> float:
    g = z[cls == 2]
    return float(np.percentile(g, 20)) if len(g) >= 20 else float(np.percentile(z, 5))


def roof_grid(x: np.ndarray, y: np.ndarray, z: np.ndarray, cls: np.ndarray, x0: float, y0: float, n: int
              ) -> tuple[np.ndarray, np.ndarray]:
    """(max height above ground per cell, point count per cell) over an n x n grid; NaN where empty."""
    keep = ~np.isin(cls, DROP_CLASSES)
    h = z - ground_level(z, cls)
    ix = np.floor((x - x0) / CELL_M).astype(int)
    iy = np.floor((y - y0) / CELL_M).astype(int)
    ok = keep & (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n)
    top = np.full((n, n), -np.inf)
    np.maximum.at(top, (iy[ok], ix[ok]), h[ok])
    count = np.zeros((n, n), int)
    np.add.at(count, (iy[ok], ix[ok]), 1)
    top[~np.isfinite(top)] = np.nan
    return top, count


def components(top: np.ndarray) -> list[Component]:
    """Connected roof-height areas, each with a closed polygon in grid metres."""
    filled = np.nan_to_num(top, nan=-1.0)
    roof = (filled >= MIN_ROOF_HEIGHT_M) & (filled <= MAX_ROOF_HEIGHT_M)
    roof = ndimage.binary_closing(roof, structure=np.ones((3, 3)), iterations=1)
    lab, n = ndimage.label(roof, structure=np.ones((3, 3)))
    out = []
    for i in range(1, n + 1):
        mask = lab == i
        area = float(mask.sum()) * CELL_M**2
        if area < MIN_COMPONENT_M2:
            continue
        cells = [box(c * CELL_M, r * CELL_M, (c + 1) * CELL_M, (r + 1) * CELL_M) for r, c in zip(*np.nonzero(mask),
                                                                                                strict=True)]
        poly = union_all(cells).buffer(1.0).buffer(-1.0)
        if poly.geom_type == "MultiPolygon":
            poly = max(poly.geoms, key=lambda g: g.area)
        poly = poly.simplify(0.4)
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        spread = (ndimage.maximum_filter(np.where(mask, filled, -np.inf), size=3)
                  - ndimage.minimum_filter(np.where(mask, filled, np.inf), size=3))
        out.append(Component(mask, poly, area, float((spread[mask] > ROUGH_RANGE_M).mean()),
                             float(np.percentile(filled[mask], 90))))
    return out


def choose(comps: list[Component], point: Point) -> Component:
    """Nearest smooth component; AmbiguousBuilding when a comparable one stands within the gap."""
    smooth = [c for c in comps if c.rough_share <= MAX_ROUGH_SHARE]
    if not smooth:
        raise FootprintError("The LiDAR shows no smooth roof near the point (only trees or noise).")
    smooth.sort(key=lambda c: c.polygon.distance(point))
    best = smooth[0]
    if best.polygon.distance(point) > MAX_POINT_DIST_M:
        raise FootprintError("No roof-height surface lies near the point in the LiDAR.")
    for other in smooth[1:]:
        if other.area_m2 >= AMBIGUOUS_RATIO * best.area_m2 and best.polygon.distance(other.polygon) <= AMBIGUOUS_GAP_M:
            raise AmbiguousBuilding("Two buildings of similar size stand close to this point.")
    area_ratio = best.polygon.area / best.area_m2
    if area_ratio > MAX_AREA_RATIO:
        raise FootprintError(f"The LiDAR outline is implausible (hull {area_ratio:.1f}x the roof cells).")
    return best


def hull_from_points(pc: lidar.PointCloud, lat: float, lng: float) -> Footprint:
    """Footprint (WGS84) of the building nearest the point, from a point cloud in ``pc.meta['epsg']``."""
    epsg = int(pc.meta.get("epsg") or utm_epsg_for(lng, lat))
    px, py = Transformer.from_crs(4326, epsg, always_xy=True).transform(lng, lat)
    x0, y0 = px - SEARCH_HALF_M, py - SEARCH_HALF_M
    n = int(2 * SEARCH_HALF_M / CELL_M)
    top, _ = roof_grid(pc.x, pc.y, pc.z, pc.classification, x0, y0, n)
    best = choose(components(top), Point(px - x0, py - y0))
    poly_m = Polygon([(x + x0, y + y0) for x, y in best.polygon.exterior.coords])
    poly = orient(project_geometry(poly_m, epsg, 4326), 1.0)
    fp = Footprint(provider="lidar_hull", id="lidar_hull", polygon_wgs84=poly, height_ft=best.height_m * FT_PER_M,
                   area_sqft=area_sqft(poly), parcel_id=None, match="nearest", source="lidar_hull")
    fp.warn("footprint_lidar_hull", HULL_NOTE)
    return fp


def fetch_hull(lat: float, lng: float, deadline: Deadline | None = None) -> Footprint:
    """Fetch LiDAR around the point (no footprint known yet) and derive the outline."""
    if deadline:
        deadline.check("footprint_hull")
    try:
        pc = lidar.fetch_best_points(lat, lng, SEARCH_HALF_M, utm_epsg_for(lng, lat), min_points=2000,
                                     footprint_m=None)
    except lidar.LidarUnavailable as exc:
        raise FootprintUnavailable(f"No LiDAR to derive an outline from: {exc}") from exc
    except lidar.LidarError as exc:
        raise FootprintError(f"No LiDAR to derive an outline from: {exc}") from exc
    pc.meta.setdefault("epsg", utm_epsg_for(lng, lat))
    return hull_from_points(pc, lat, lng)
