"""LA County link of the footprint chain: parcel by situs address, then LARIAC 2020 building outlines.

WHY the algorithm: the geocoder point sits in the street, so a parcel is found by querying a 60 m radius,
scoring each parcel's situs address against the input, and then asking the building layer what intersects
that parcel. The layer is keyless and carries a roof height. Outside the county the parcel query is empty
and the chain moves on.
"""

from __future__ import annotations

import json
import logging

from shapely.geometry import Point, Polygon, shape

from . import cache
from .footprint_types import (
    Footprint,
    address_tokens,
    area_sqft,
    as_polygon,
)
from .frame import project_geometry, utm_epsg_for
from .geocode import Address

log = logging.getLogger(__name__)

PARCEL_URL = ("https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/"
              "LACounty_Parcel/MapServer/0/query")
BUILDING_URL = ("https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
                "Countywide_Building_Outlines_(2020)/FeatureServer/0/query")
# The parcel layer covers LA County only: elsewhere skip the call (a county outage must not cost a national address time).
LA_BBOX = (33.7, 34.83, -118.95, -117.65)  # lat min/max, lng min/max
MIN_PARCEL_OVERLAP = 0.5  # a building counts for a parcel when at least this share of it lies inside

Note = tuple[str, str]  # (warning code, text)


def score_parcel(props: dict, address: Address) -> int:
    """How well a parcel's situs address matches the input (higher is better)."""
    num, direction, street = address_tokens(address.line1)
    score = 0
    if num and str(props.get("SitusHouseNo", "")).strip() == num:
        score += 4
    if street and street in str(props.get("SitusStreet", "")).upper().split():
        score += 4
    if direction and str(props.get("SitusDirection", "")).strip().upper() == direction:
        score += 1
    return score


def pick_parcel(features: list[dict], lat: float, lng: float, address: Address) -> tuple[dict, str]:
    """Choose the parcel and say how it matched: 'exact' (house number and street), 'street' or 'nearest'.

    WHY the number comes first: the geocoder interpolates along the street, so the nearest parcel is
    often a neighbour. Only parcels whose situs number equals the input are considered while any exist.
    """
    pt = Point(lng, lat)
    num = address_tokens(address.line1)[0]

    def dist(f: dict) -> float:
        return shape(f["geometry"]).distance(pt) if f.get("geometry") else 1e9

    def key(f: dict) -> tuple[int, float]:
        return (-score_parcel(f["properties"], address), dist(f))

    same_num = [f for f in features if num and str(f["properties"].get("SitusHouseNo", "")).strip() == num]
    pool = same_num or features
    best = min(pool, key=key)
    if same_num and score_parcel(best["properties"], address) >= 8:
        return best, "exact"
    if same_num:
        return best, "street"
    return best, "nearest"


def _esri_rings(parcel: Polygon) -> list[list[list[float]]]:
    return [[list(c) for c in parcel.exterior.coords]] + [[list(c) for c in r.coords] for r in parcel.interiors]


def _arcgis_check(obj: dict) -> None:
    """ArcGIS answers HTTP 200 with {"error": ...} on failure; that must neither be cached nor read as 'empty'."""
    if isinstance(obj, dict) and "error" in obj:
        raise cache.BadResponse(f"ArcGIS error: {str(obj['error'])[:200]}")


def fetch_county(lat: float, lng: float, address: Address) -> tuple[Footprint | None, list[Note]]:
    """(footprint or None, notes for the footprint that replaces it).

    A matched parcel with no building outline is no longer fatal: it returns None plus a
    ``parcel_without_building`` note and the chain tries OpenStreetMap; a failing layer query does the same with
    a note. This link never raises for an outage.
    """
    if not (LA_BBOX[0] <= lat <= LA_BBOX[1] and LA_BBOX[2] <= lng <= LA_BBOX[3]):
        return None, []
    pq = {"f": "geojson", "geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
          "spatialRel": "esriSpatialRelIntersects", "distance": 60, "units": "esriSRUnit_Meter",
          "outFields": "*", "outSR": 4326, "returnGeometry": "true"}
    try:
        parcels = cache.fetch_json(PARCEL_URL, params=pq, check=_arcgis_check).get("features", [])
    except cache.NET_ERRORS as e:
        # An unreachable layer is NOT "outside the county": say so on whatever footprint replaces it.
        log.info("LA County parcel query failed: %s", cache.describe_error(e))
        return None, [("other", "LA County layer unreachable; footprint from OpenStreetMap.")]
    parcels = [f for f in parcels if f.get("geometry")]
    if not parcels:
        return None, []  # genuinely outside the county layer
    parcel, match = pick_parcel(parcels, lat, lng, address)
    warnings: list[Note] = []
    if match != "exact":
        text = (f"Address {address.line1} has no exact parcel match; used parcel "
                f"{parcel['properties'].get('SitusAddress')} ({match} match).")
        warnings.append(("other", text))
    parcel_poly = as_polygon(parcel["geometry"])
    bq = {"f": "geojson", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
          "outSR": 4326, "returnGeometry": "true", "geometryType": "esriGeometryPolygon",
          "geometry": json.dumps({"rings": _esri_rings(parcel_poly), "spatialReference": {"wkid": 4326}})}
    try:
        feats = cache.fetch_json(BUILDING_URL, method="POST", data=bq, check=_arcgis_check).get("features", [])
    except cache.NET_ERRORS as e:
        log.info("LA County building query failed: %s", cache.describe_error(e))
        text = (f"The LA County building layer could not be queried ({cache.describe_error(e)}); "
                "footprint taken from another source.")
        return None, [*warnings, ("other", text)]
    c = parcel_poly.centroid
    epsg = utm_epsg_for(c.x, c.y)
    parcel_m = project_geometry(parcel_poly, 4326, epsg)
    scored = []
    for f in feats:
        if not f.get("geometry"):
            continue
        poly = as_polygon(f["geometry"])
        bm = project_geometry(poly, 4326, epsg)
        inter = bm.intersection(parcel_m).area
        scored.append((inter, inter / bm.area if bm.area else 0.0, f, poly))
    # WHY overlap and not "intersects + largest": a big neighbour that merely touches the parcel edge
    # is returned by the intersects query and used to win on size.
    ok = [t for t in scored if t[1] >= MIN_PARCEL_OVERLAP]
    if not ok:
        if match in ("exact", "street"):
            # The geocode point is on the street, so OSM may pick a building across it: say so on the result.
            text = ("The parcel matched but has no building outline in the county layer "
                    f"(parcel {parcel['properties'].get('AIN')}); footprint taken from another source.")
            warnings.append(("parcel_without_building", text))
        return None, warnings
    ok.sort(key=lambda t: t[0], reverse=True)
    _, _, main_f, main = ok[0]
    props = main_f["properties"]
    area = props.get("AREA")
    fp = Footprint(
        provider="lacounty_lariac_2020",
        id=str(props.get("BLD_ID") or props.get("OBJECTID")),
        polygon_wgs84=main,
        height_ft=float(props["HEIGHT"]) if props.get("HEIGHT") else None,
        area_sqft=float(area) if area else area_sqft(main),
        parcel_id=str(parcel["properties"].get("AIN")) if parcel["properties"].get("AIN") else None,
        other_buildings=[t[3] for t in ok[1:]], match=match, source="lariac")
    for code, text in warnings:
        fp.warn(code, text)
    return fp, []

