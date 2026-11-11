"""Footprint value types and helpers shared by the footprint links (county, OSM, Solar, LiDAR hull)."""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.polygon import orient

from .frame import FT_PER_M, project_geometry, utm_epsg_for

SQFT_PER_M2 = FT_PER_M**2
SOURCES = ("lariac", "osm", "solar", "lidar_hull")


class FootprintError(RuntimeError):
    """No building footprint could be found near the address."""


class FootprintUnavailable(FootprintError):
    """A footprint source could not be reached (outage, rate limit): retryable, not 'no building here'."""


class AmbiguousBuilding(FootprintError):
    """Two buildings of similar size stand close to the point, so the roof to measure is unclear."""


@dataclass
class Footprint:
    provider: str
    id: str
    polygon_wgs84: Polygon
    height_ft: float | None
    area_sqft: float
    parcel_id: str | None
    other_buildings: list[Polygon] = field(default_factory=list)
    match: str = "exact"  # exact | street | nearest: how well the address matched the chosen parcel/building
    warnings: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)  # parallel to warnings (closed list, see envelope)
    source: str = "lariac"  # one of SOURCES: which link of the chain produced it

    def warn(self, code: str, text: str) -> None:
        self.warnings.append(text)
        self.warning_codes.append(code)


def area_sqft(poly: Polygon) -> float:
    c = poly.centroid
    return float(project_geometry(poly, 4326, utm_epsg_for(c.x, c.y)).area * SQFT_PER_M2)


def as_polygon(geom_json: dict) -> Polygon:
    g = shape(geom_json)
    if isinstance(g, MultiPolygon):
        g = max(g.geoms, key=lambda p: p.area)
    return orient(g.buffer(0) if not g.is_valid else g, sign=1.0)


def address_tokens(line1: str) -> tuple[str, str, str]:
    """(house number, direction N/S/E/W or '', street name without suffix) upper-cased."""
    parts = line1.upper().split()
    num = parts[0] if parts and parts[0].isdigit() else ""
    rest = parts[1:] if num else parts
    direction = ""
    if rest and rest[0] in {"N", "S", "E", "W", "NORTH", "SOUTH", "EAST", "WEST"}:
        direction = rest[0][0]
        rest = rest[1:]
    return num, direction, rest[0] if rest else ""
