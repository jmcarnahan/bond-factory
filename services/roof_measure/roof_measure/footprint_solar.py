"""Google Solar link of the footprint chain (plan D6): used only when a Solar key is set.

``buildingInsights`` has no outline polygon, so the footprint is the convex hull of the corners of every roof
segment's bounding box. That over-states concave plans (L and U shapes), which is why the chain marks the
source ``solar``, caps the confidence at 0.5 and never lets the verdict be ``pass``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from shapely.geometry import MultiPoint, Polygon
from shapely.geometry.polygon import orient

from . import solar
from .deadline import Deadline
from .errors import is_transient
from .footprint_types import Footprint, FootprintUnavailable, area_sqft

log = logging.getLogger(__name__)
SOLAR_NOTE = ("Footprint estimated from Google Solar roof segments (convex hull of segment boxes); "
              "it can be larger than the real outline.")


def solar_key(env: dict[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    for name in ("GOOGLE_SOLAR_API_KEY",):
        if env.get(name):
            return env[name]
    return None


def hull_from_insights(insights: dict[str, Any]) -> Polygon | None:
    """Convex hull (lng, lat) of all segment bounding-box corners; None when there are no usable segments."""
    pts: list[tuple[float, float]] = []
    for sg in insights.get("solarPotential", {}).get("roofSegmentStats", []):
        bb = sg.get("boundingBox") or {}
        try:
            sw, ne = bb["sw"], bb["ne"]
            for lat in (sw["latitude"], ne["latitude"]):
                for lng in (sw["longitude"], ne["longitude"]):
                    pts.append((float(lng), float(lat)))
        except (KeyError, TypeError, ValueError):
            continue
    if len(pts) < 3:
        return None
    hull = MultiPoint(pts).convex_hull
    return orient(hull, 1.0) if isinstance(hull, Polygon) and hull.area > 0 else None


def footprint_from_insights(insights: dict[str, Any]) -> Footprint | None:
    hull = hull_from_insights(insights)
    if hull is None:
        return None
    fp = Footprint(provider="solar", id=str(insights.get("name") or "solar"), polygon_wgs84=hull, height_ft=None,
                   area_sqft=area_sqft(hull), parcel_id=None, match="nearest", source="solar")
    fp.warn("footprint_solar", SOLAR_NOTE)
    return fp


def fetch_solar(lat: float, lng: float, key: str, deadline: Deadline | None = None) -> Footprint | None:
    """None when Solar has no building here (or is disabled); FootprintUnavailable on an outage."""
    timeout = deadline.timeout(20.0) if deadline else 20.0
    try:
        insights = solar.fetch_building_insights(lat, lng, key, timeout=timeout)
    except solar.SolarUnavailable as exc:
        log.info("Solar footprint unavailable: %s", type(exc).__name__)
        if is_transient(exc):  # 429, 5xx, connection: an outage, not "Solar has no building here"
            raise FootprintUnavailable("Google Solar could not be reached") from None
        return None
    return footprint_from_insights(insights)
