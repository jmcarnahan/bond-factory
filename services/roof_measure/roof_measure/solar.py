"""Google Solar API ``buildingInsights`` -> evidence rows in the model frame.

WHY evidence rows: the Claude agent (and the deterministic fallback) reason about roof
segments placed on the footprint in feet, not about WGS84 boxes. This module does the
placement once, so the agent never converts coordinates itself.

The Solar API is DISABLED on our Google project at the time of writing, so the live path is
coded and fails with :class:`SolarUnavailable` (clear message plus the enable URL); the
service is exercised with the synthetic fixture in ``fixtures/solar_site1_fixture.json``.
Never log the API key: request errors are rewritten before they leave this module.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import requests
from pyproj import Transformer
from shapely.geometry import Point, Polygon, box

from .classify import Block, BlockSet

log = logging.getLogger(__name__)

ENABLE_URL = "https://console.developers.google.com/apis/api/solar.googleapis.com/overview?project=<gcp-project-number>"
INSIGHTS_URL = "https://solar.googleapis.com/v1/buildingInsights:findClosest"
M2_TO_FT2 = 10.7639
M_TO_FT = 1.0 / 0.3048
FLAT_BELOW_DEG = 2.0  # Solar segments flatter than this are flat roofs


class SolarUnavailable(RuntimeError):
    """The Solar API cannot answer (disabled, no coverage, or key rejected)."""


def fetch_building_insights(lat: float, lng: float, api_key: str, timeout: float = 30.0) -> dict[str, Any]:
    """Live ``buildingInsights:findClosest`` with ``requiredQuality=HIGH``.

    Raises :class:`SolarUnavailable` on 403/404 (API disabled, key not allowed, or no HIGH
    quality coverage) with the console URL that enables the API.
    """
    params = {"location.latitude": f"{lat:.7f}", "location.longitude": f"{lng:.7f}",
              "requiredQuality": "HIGH", "key": api_key}
    try:
        r = requests.get(INSIGHTS_URL, params=params, timeout=timeout)
    except requests.RequestException as exc:  # message of requests errors embeds the URL, key included
        raise SolarUnavailable(f"Solar API request failed ({type(exc).__name__}); key not shown.") from None
    if r.status_code in (403, 404):
        reason = ""
        try:
            reason = r.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        what = ("The Solar API is not enabled or this key is not allowed to use it" if r.status_code == 403
                else "The Solar API has no HIGH quality building at this location, or the API is not enabled")
        raise SolarUnavailable(f"{what} (HTTP {r.status_code}: {reason[:160]}). "
                               f"Enable it at {ENABLE_URL} and retry.")
    if not r.ok:
        raise SolarUnavailable(f"Solar API returned HTTP {r.status_code}.")
    return r.json()


def load_fixture(path: str | Path) -> dict[str, Any]:
    """Read a saved/synthetic ``buildingInsights`` document."""
    return json.loads(Path(path).read_text())


def insights_meta(insights: dict[str, Any], live: bool = False) -> dict[str, Any]:
    """``source.solar`` object of the contract."""
    d = insights.get("imageryDate") or {}
    date = f"{d.get('year', 0):04d}-{d.get('month', 1):02d}-{d.get('day', 1):02d}" if d else None
    return {"imagery_date": date, "imagery_quality": insights.get("imageryQuality"),
            "segments": len(insights.get("solarPotential", {}).get("roofSegmentStats", [])),
            "synthetic": bool(insights.get("_SYNTHETIC")) or not live}


def segments_to_evidence(insights: dict[str, Any], frame: dict[str, Any],
                         footprint_ft: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Place each ``roofSegmentStats`` entry on the footprint, in feet.

    ``frame`` is the blocks-file frame (``epsg``, ``x0_m``, ``y0_m``). Each row has
    ``pitch_rise``, ``azimuth_deg``, ``area_sqft`` (tilted), ``ground_area_sqft``, ``bbox_ft``
    ``[minx, miny, maxx, maxy]``, ``center_ft``, whether the centre is inside the footprint and
    its distance to it, and a flat/sloped hint (pitch < 2 deg is flat).
    """
    tf = Transformer.from_crs(4326, int(frame["epsg"]), always_xy=True)
    x0, y0 = float(frame["x0_m"]), float(frame["y0_m"])

    def to_ft(lng: float, lat: float) -> tuple[float, float]:
        x, y = tf.transform(lng, lat)
        return ((x - x0) * M_TO_FT, (y - y0) * M_TO_FT)

    fp = Polygon(footprint_ft).buffer(0)
    rows = []
    for k, sg in enumerate(insights.get("solarPotential", {}).get("roofSegmentStats", [])):
        c = sg["center"]
        cx, cy = to_ft(c["longitude"], c["latitude"])
        bb = sg["boundingBox"]
        sw = to_ft(bb["sw"]["longitude"], bb["sw"]["latitude"])
        ne = to_ft(bb["ne"]["longitude"], bb["ne"]["latitude"])
        pt = Point(cx, cy)
        deg = float(sg["pitchDegrees"])
        rows.append({
            "id": f"s{k}",
            "pitch_degrees": deg,
            "pitch_rise": 12.0 * math.tan(math.radians(deg)),
            "azimuth_deg": float(sg["azimuthDegrees"]),
            "area_sqft": sg["stats"]["areaMeters2"] * M2_TO_FT2,
            "ground_area_sqft": sg["stats"]["groundAreaMeters2"] * M2_TO_FT2,
            "bbox_ft": [min(sw[0], ne[0]), min(sw[1], ne[1]), max(sw[0], ne[0]), max(sw[1], ne[1])],
            "center_ft": [cx, cy],
            "plane_height_m": sg.get("planeHeightAtCenterMeters"),
            "inside_footprint": bool(fp.contains(pt)),
            "dist_to_footprint_ft": float(fp.distance(pt)),
            "form_hint": "flat" if deg < FLAT_BELOW_DEG else "sloped",
        })
    return rows


def evidence_to_blockset(evidence: list[dict[str, Any]], base: BlockSet) -> BlockSet:
    """Turn Solar evidence into a LiDAR-style block set so the deterministic classifier can run.

    Each segment becomes a block whose polygon is its bounding box (clipped to the footprint
    unless the segment centre lies outside it, which marks an awning). Boxes are crude: this
    is the ``--no-agent`` fallback and the baseline the agent should beat.
    """
    fp = base.footprint
    blocks: list[Block] = []
    for e in evidence:
        b = box(*e["bbox_ft"])
        poly = b if (not e["inside_footprint"] and e["form_hint"] == "sloped") else b.intersection(fp)
        if poly.is_empty or poly.geom_type != "Polygon" or poly.area < 1.0:
            continue
        z = (e.get("plane_height_m") or 0.0) * M_TO_FT
        blocks.append(Block(
            id=e["id"], kind="flat" if e["form_hint"] == "flat" else "sloped",
            polygon_ft=[(float(x), float(y)) for x, y in list(poly.exterior.coords)[:-1]],
            plan_area_sqft=e["ground_area_sqft"], mean_z_ft=z, height_above_ground_ft=z,
            pitch_rise=0.0 if e["form_hint"] == "flat" else e["pitch_rise"],
            aspect_deg=None if e["form_hint"] == "flat" else e["azimuth_deg"]))
    return BlockSet(address=base.address, origin=base.origin, frame=base.frame, footprint_ft=base.footprint_ft,
                    footprint_meta=base.footprint_meta, lidar={}, blocks=blocks, borders=[], outline_edges=[],
                    extra={"derived_from": "solar_segments"})
