"""Coordinate frame shared by every stage (contract section 1).

WHY: footprints arrive in WGS84, LiDAR in EPSG:3857 and the model is published in feet with
the origin at the south-west corner of the footprint bbox. One small object owns every
conversion so no stage re-derives an offset and drifts from the others.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from shapely import transform as shp_transform
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

FT_PER_M = 1.0 / 0.3048
M_PER_FT = 0.3048


def utm_epsg_for(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing (lon, lat).

    WHY: metric work (rasters, plane fits) needs a conformal metric CRS; choosing the zone
    from longitude keeps the service usable outside UTM 11N (Los Angeles).
    """
    zone = int((lon + 180.0) // 6.0) % 60 + 1
    return (32600 if lat >= 0 else 32700) + zone


def _tf(src: int, dst: int) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def project_geometry(geom: BaseGeometry, src_epsg: int, dst_epsg: int) -> BaseGeometry:
    """Reproject any shapely geometry (lon/lat order is x/y for 4326)."""
    t = _tf(src_epsg, dst_epsg)

    def _f(a: np.ndarray) -> np.ndarray:
        x, y = t.transform(a[:, 0], a[:, 1])
        return np.column_stack([x, y])

    return shp_transform(geom, _f)


@dataclass(frozen=True)
class Frame:
    """Metric CRS plus the translation to the model's feet frame.

    `[0, 0]` ft is (x0_m, y0_m) in `epsg`; `origin_lat/lng` is that same point in WGS84.
    """

    epsg: int
    x0_m: float
    y0_m: float
    origin_lat: float
    origin_lng: float

    def to_ft(self, xy_m: np.ndarray | tuple[float, float]) -> np.ndarray:
        """Metric CRS point(s) -> feet in the model frame. Accepts (2,) or (N, 2)."""
        a = np.asarray(xy_m, dtype=float)
        out = (a - np.array([self.x0_m, self.y0_m])) * FT_PER_M
        return out

    def to_m(self, xy_ft: np.ndarray | tuple[float, float]) -> np.ndarray:
        """Feet in the model frame -> metric CRS point(s)."""
        a = np.asarray(xy_ft, dtype=float)
        return a * M_PER_FT + np.array([self.x0_m, self.y0_m])

    def local_m(self, xy_m: np.ndarray) -> np.ndarray:
        """Metric CRS -> metres relative to the frame origin (what the raster code uses)."""
        return np.asarray(xy_m, dtype=float) - np.array([self.x0_m, self.y0_m])

    @classmethod
    def from_footprint_m(cls, footprint_m: Polygon, epsg: int) -> Frame:
        """Frame whose origin is the SW corner of the footprint bbox (already in `epsg`)."""
        minx, miny, _, _ = footprint_m.bounds
        lng, lat = _tf(epsg, 4326).transform(minx, miny)
        return cls(epsg=epsg, x0_m=float(minx), y0_m=float(miny), origin_lat=float(lat), origin_lng=float(lng))

    @classmethod
    def for_footprint(cls, footprint_wgs84: Polygon) -> tuple[Frame, Polygon]:
        """Pick the UTM zone from the footprint centroid; return (frame, footprint in metres)."""
        c = footprint_wgs84.centroid
        epsg = utm_epsg_for(c.x, c.y)
        fp_m = project_geometry(footprint_wgs84, 4326, epsg)
        return cls.from_footprint_m(fp_m, epsg), fp_m  # type: ignore[arg-type]
