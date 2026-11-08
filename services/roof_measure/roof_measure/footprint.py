"""Building footprint for an address.

WHY the algorithm: the geocoder point sits in the street, so a parcel is found by querying
a 60 m radius, scoring each parcel's situs address against the input, and then asking the
building layer what intersects that parcel. LA County (LARIAC 2020 outlines) is keyless and
carries a roof height; OSM Overpass is the generic fallback outside the county.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.geometry.polygon import orient

from . import cache
from .frame import FT_PER_M, project_geometry, utm_epsg_for
from .geocode import Address

log = logging.getLogger(__name__)

PARCEL_URL = ("https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/"
              "LACounty_Parcel/MapServer/0/query")
BUILDING_URL = ("https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
                "Countywide_Building_Outlines_(2020)/FeatureServer/0/query")
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter")
SQFT_PER_M2 = FT_PER_M**2
MIN_PARCEL_OVERLAP = 0.5  # a building counts for a parcel when at least this share of it lies inside
MIN_OSM_SQFT = 400.0
MAX_OSM_CENTROID_M = 30.0


class FootprintError(RuntimeError):
    """No building footprint could be found near the address."""


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


def _area_sqft(poly: Polygon) -> float:
    c = poly.centroid
    return float(project_geometry(poly, 4326, utm_epsg_for(c.x, c.y)).area * SQFT_PER_M2)


def _as_polygon(geom_json: dict) -> Polygon:
    g = shape(geom_json)
    if isinstance(g, MultiPolygon):
        g = max(g.geoms, key=lambda p: p.area)
    return orient(g.buffer(0) if not g.is_valid else g, sign=1.0)


# ---------------------------------------------------------------- parcels
def _tokens(line1: str) -> tuple[str, str, str]:
    """(house number, direction N/S/E/W or '', street name without suffix) upper-cased."""
    parts = line1.upper().split()
    num = parts[0] if parts and parts[0].isdigit() else ""
    rest = parts[1:] if num else parts
    direction = ""
    if rest and rest[0] in {"N", "S", "E", "W", "NORTH", "SOUTH", "EAST", "WEST"}:
        direction = rest[0][0]
        rest = rest[1:]
    return num, direction, rest[0] if rest else ""


def score_parcel(props: dict, address: Address) -> int:
    """How well a parcel's situs address matches the input (higher is better)."""
    num, direction, street = _tokens(address.line1)
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
    num = _tokens(address.line1)[0]

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


def _county(lat: float, lng: float, address: Address) -> tuple[Footprint | None, list[str]]:
    """(footprint or None, warnings for the caller). Raises FootprintError when a matched parcel has no building."""
    pq = {"f": "geojson", "geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
          "spatialRel": "esriSpatialRelIntersects", "distance": 60, "units": "esriSRUnit_Meter",
          "outFields": "*", "outSR": 4326, "returnGeometry": "true"}
    try:
        parcels = cache.fetch_json(PARCEL_URL, params=pq, check=_arcgis_check).get("features", [])
    except cache.NET_ERRORS as e:
        # An unreachable layer is NOT "outside the county": say so on whatever footprint replaces it.
        log.info("LA County parcel query failed: %s", e)
        return None, ["LA County layer unreachable; footprint from OpenStreetMap."]
    parcels = [f for f in parcels if f.get("geometry")]
    if not parcels:
        return None, []  # genuinely outside the county layer
    parcel, match = pick_parcel(parcels, lat, lng, address)
    warnings: list[str] = []
    if match != "exact":
        warnings.append(f"Address {address.line1} has no exact parcel match; used parcel "
                        f"{parcel['properties'].get('SitusAddress')} ({match} match).")
    parcel_poly = _as_polygon(parcel["geometry"])
    bq = {"f": "geojson", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
          "outSR": 4326, "returnGeometry": "true", "geometryType": "esriGeometryPolygon",
          "geometry": json.dumps({"rings": _esri_rings(parcel_poly), "spatialReference": {"wkid": 4326}})}
    try:
        feats = cache.fetch_json(BUILDING_URL, method="POST", data=bq, check=_arcgis_check).get("features", [])
    except cache.NET_ERRORS as e:
        raise FootprintError(f"Parcel {parcel['properties'].get('AIN')} matched, but the LA County building "
                             f"layer could not be queried ({e}).") from e
    c = parcel_poly.centroid
    epsg = utm_epsg_for(c.x, c.y)
    parcel_m = project_geometry(parcel_poly, 4326, epsg)
    scored = []
    for f in feats:
        if not f.get("geometry"):
            continue
        poly = _as_polygon(f["geometry"])
        bm = project_geometry(poly, 4326, epsg)
        inter = bm.intersection(parcel_m).area
        scored.append((inter, inter / bm.area if bm.area else 0.0, f, poly))
    # WHY overlap and not "intersects + largest": a big neighbour that merely touches the parcel edge
    # is returned by the intersects query and used to win on size.
    ok = [t for t in scored if t[1] >= MIN_PARCEL_OVERLAP]
    if not ok:
        if match in ("exact", "street"):
            # WHY not OSM: the geocode point is on the street, so OSM would pick a building across it.
            raise FootprintError("parcel matched but has no building outline "
                                 f"(parcel {parcel['properties'].get('AIN')}, {parcel['properties'].get('SitusAddress')}).")
        return None, warnings
    ok.sort(key=lambda t: t[0], reverse=True)
    _, _, main_f, main = ok[0]
    props = main_f["properties"]
    area = props.get("AREA")
    return Footprint(
        provider="lacounty_lariac_2020",
        id=str(props.get("BLD_ID") or props.get("OBJECTID")),
        polygon_wgs84=main,
        height_ft=float(props["HEIGHT"]) if props.get("HEIGHT") else None,
        area_sqft=float(area) if area else _area_sqft(main),
        parcel_id=str(parcel["properties"].get("AIN")) if parcel["properties"].get("AIN") else None,
        other_buildings=[t[3] for t in ok[1:]], match=match, warnings=warnings,
    ), []


# ---------------------------------------------------------------- OSM
def _overpass_check(obj: dict) -> None:
    """Overpass reports timeouts and load shedding as a `remark` on a 200 response with no elements."""
    if isinstance(obj, dict) and obj.get("remark"):
        raise cache.BadResponse(f"Overpass remark: {str(obj['remark'])[:200]}")


def _osm(lat: float, lng: float, address: Address | None = None) -> Footprint | None:
    q = (f'[out:json][timeout:60];way["building"](around:40,{lat},{lng});out geom tags;')
    payload = None
    failures: list[str] = []
    for url in OVERPASS_URLS:
        try:
            payload = cache.fetch_json(url, method="POST", data={"data": q}, timeout=70, retries=0,
                                       check=_overpass_check)
            break
        except cache.NET_ERRORS as e:
            log.info("Overpass %s failed: %s", url, e)
            failures.append(f"{url}: {e}")
    if payload is None:
        raise FootprintError("OpenStreetMap (Overpass) could not be reached, so no fallback footprint is "
                             "available: " + "; ".join(failures)[:300])
    pt = Point(lng, lat)
    cands: list[tuple[dict, Polygon, float, float]] = []  # (element, polygon, area sqft, centroid distance m)
    for el in payload.get("elements", []):
        geom = el.get("geometry") or []
        if el.get("type") != "way" or len(geom) < 4:
            continue
        poly = Polygon([(p["lon"], p["lat"]) for p in geom])
        if poly.is_valid and not poly.is_empty:
            poly = orient(poly, 1.0)
            c = poly.centroid
            d_m = Point(c.x, c.y).distance(pt) * 111_000 * 0.83
            cands.append((el, poly, _area_sqft(poly), d_m))
    if not cands:
        return None
    warnings: list[str] = []
    match = "nearest"
    num = _tokens(address.line1)[0] if address else ""
    tagged = [c for c in cands if num and str(c[0].get("tags", {}).get("addr:housenumber", "")) == num]
    if tagged:
        pool, match = tagged, "exact"
    else:
        # WHY: the geocode point is in the street, so "nearest" picks a shed. Take the largest real building.
        pool = [c for c in cands if c[2] >= MIN_OSM_SQFT and c[3] <= MAX_OSM_CENTROID_M]
        if not pool:
            pool = sorted(cands, key=lambda c: c[3])[:1]
            warnings.append("Only a small or distant OSM building was found; verify it is the right one.")
    el, main, area, _ = max(pool, key=lambda c: c[2])
    tags = el.get("tags", {})
    height = None
    m = re.match(r"\s*([\d.]+)", str(tags.get("height", "")))
    if m:
        height = float(m.group(1)) * FT_PER_M
    warnings.append("Footprint from OpenStreetMap; no parcel match or roof height from the county.")
    return Footprint(provider="osm", id=str(el["id"]), polygon_wgs84=main, height_ft=height,
                     area_sqft=area, parcel_id=None, other_buildings=[c[1] for c in cands if c[0] is not el],
                     match=match, warnings=warnings)


def fetch_footprint(lat: float, lng: float, address: Address) -> Footprint:
    """LA County outlines first, OSM second; `FootprintError` when neither has a building."""
    fp, notes = _county(lat, lng, address)
    if fp is None:
        fp = _osm(lat, lng, address)
        if fp is not None:
            fp.warnings = [*notes, *fp.warnings]
    if fp is None:
        raise FootprintError(f"No building footprint found near {address.line1}, {address.city}. "
                             "LA County and OpenStreetMap have nothing within 60 m.")
    return fp
