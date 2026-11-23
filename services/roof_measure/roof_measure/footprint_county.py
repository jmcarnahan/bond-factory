"""LA County link of the footprint chain: parcel by situs address, then LARIAC 2020 building outlines.

WHY the algorithm: the geocoder point sits in the street, so a parcel is found by querying a 60 m radius,
scoring each parcel's situs address against the input, and then asking the building layer what intersects
that parcel. The layer is keyless and carries a roof height. Outside the county the parcel query is empty
and the chain moves on.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from shapely.geometry import Point, Polygon, shape

from . import cache
from .footprint_types import (
    Footprint,
    FootprintError,
    address_tokens,
    area_sqft,
    as_polygon,
)
from .frame import project_geometry, utm_epsg_for
from .geocode import Address
from .street_names import same_street, street_key

log = logging.getLogger(__name__)

PARCEL_URL = ("https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/"
              "LACounty_Parcel/MapServer/0/query")
BUILDING_URL = ("https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
                "Countywide_Building_Outlines_(2020)/FeatureServer/0/query")
# The parcel layer covers LA County only: elsewhere skip the call (a county outage must not cost a national address time).
LA_BBOX = (33.7, 34.83, -118.95, -117.65)  # lat min/max, lng min/max
MIN_PARCEL_OVERLAP = 0.5  # a building counts for a parcel when at least this share of it lies inside
NEARBY_RADIUS_M = 60.0  # buildings this close to the lookup point are reported as ``nearby`` (the parcel query's own radius)
NEARBY_MAX = 8

Note = tuple[str, str]  # (warning code, text)


def _situs_key(props: dict) -> str:
    """The parcel's street as ``street_names.street_key`` text: situs direction plus situs street."""
    return street_key(f"1 {str(props.get('SitusDirection', '')).strip()} {str(props.get('SitusStreet', '')).strip()}")


def score_parcel(props: dict, address: Address) -> int:
    """How well a parcel's situs address matches the input (higher is better).

    The street compares after ``street_names`` normalisation, so "Ave B" and "AVENUE B" are the same street; a
    different street name or type is not.
    """
    num, direction, _ = address_tokens(address.line1)
    score = 0
    if num and str(props.get("SitusHouseNo", "")).strip() == num:
        score += 4
    if same_street(street_key(address.line1), _situs_key(props)):
        score += 4
    if direction and str(props.get("SitusDirection", "")).strip().upper() == direction:
        score += 1
    return score


def pick_parcel(features: list[dict], lat: float, lng: float, address: Address, *,
                point_given: bool = False) -> tuple[dict, str]:
    """Choose the parcel and say how it matched: 'exact' (house number and street), 'street' or 'nearest'.

    WHY the number comes first: the geocoder interpolates along the street, so the nearest parcel is
    often a neighbour. Only parcels whose situs number equals the input are considered while any exist.

    ``point_given``: the point is the caller's rooftop point, not a street geocode. The parcel that CONTAINS it
    is then the property (a text match on a neighbour must not win over where the roof is); several containing
    parcels (condo overlays) are told apart by the text score. With no containing parcel the rule above applies.
    The match label stays text based: 'exact' only when the situs number and street also match the input AND the
    point (when given) lies on that parcel; a point on no parcel never reports 'exact'.
    """
    pt = Point(lng, lat)
    num = address_tokens(address.line1)[0]

    def dist(f: dict) -> float:
        return shape(f["geometry"]).distance(pt) if f.get("geometry") else 1e9

    def key(f: dict) -> tuple[int, float]:
        return (-score_parcel(f["properties"], address), dist(f))

    def num_ok(f: dict) -> bool:
        return bool(num) and str(f["properties"].get("SitusHouseNo", "")).strip() == num

    if point_given:
        holding = [f for f in features if f.get("geometry") and shape(f["geometry"]).contains(pt)]
        if holding:
            best = min(holding, key=key)
            if score_parcel(best["properties"], address) >= 8:
                return best, "exact"
            return best, "street" if num_ok(best) else "nearest"
    same_num = [f for f in features if num_ok(f)]
    pool = same_num or features
    best = min(pool, key=key)
    if same_num and score_parcel(best["properties"], address) >= 8:
        # a roof point that lies on no parcel cannot confirm the text: "street" (and the caller is warned)
        return best, "street" if point_given else "exact"
    if same_num:
        return best, "street"
    return best, "nearest"


def _building_info(feature: dict, poly: Polygon) -> dict:
    props = feature["properties"]
    area = props.get("AREA")
    return {"id": _outline_id(feature, poly), "area_sqft": float(area) if area else area_sqft(poly)}


def _esri_rings(parcel: Polygon) -> list[list[list[float]]]:
    return [[list(c) for c in parcel.exterior.coords]] + [[list(c) for c in r.coords] for r in parcel.interiors]


def _arcgis_check(obj: dict) -> None:
    """ArcGIS answers HTTP 200 with {"error": ...} on failure; that must neither be cached nor read as 'empty'."""
    if isinstance(obj, dict) and "error" in obj:
        raise cache.BadResponse(f"ArcGIS error: {str(obj['error'])[:200]}")


_OUTLINE_ID = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def _real_id(feature: dict) -> str | None:
    props = feature["properties"]
    v = props.get("BLD_ID") or props.get("OBJECTID")
    return str(v) if v else None


def _outline_id(feature: dict, poly: Polygon | None = None) -> str:
    """The layer's id, or (never the text "None") a stable id from the geometry for an outline that has none."""
    real = _real_id(feature)
    if real or poly is None:
        return real or ""
    return "geo-" + hashlib.sha1(poly.wkt.encode()).hexdigest()[:12]


def _outline_lookup(outline_id: str) -> Polygon | None:
    """The county outline ``outline_id`` (WGS84); None when the layer has no such outline."""
    if not _OUTLINE_ID.match(outline_id):
        return None
    where = f"BLD_ID = '{outline_id}'" + (f" OR OBJECTID = {outline_id}" if outline_id.isdigit() else "")
    q = {"f": "geojson", "where": where, "outFields": "BLD_ID,OBJECTID", "outSR": 4326, "returnGeometry": "true",
         "resultRecordCount": 5}
    for f in cache.fetch_json(BUILDING_URL, params=q, check=_arcgis_check).get("features", []):
        if f.get("geometry") and _real_id(f) == outline_id:
            return as_polygon(f["geometry"])
    return None


def _nearby(scored: list[tuple], ok: list[tuple], chosen: tuple, lookup_m: Point) -> list[dict]:
    """The other county outlines within ``NEARBY_RADIUS_M`` of the lookup point, nearest first, at most ``NEARBY_MAX``:
    ``{"outline_id", "area_sqft", "distance_m", "on_matched_parcel"}``. An outline with no layer id is left out (it
    cannot be named in a later request). ``distance_m`` runs from the lookup point to the outline (0 inside it)."""
    out = []
    seen = {_real_id(chosen[2])}  # a building split across tiles comes back twice: one row per id
    for t in scored:
        if t is chosen or _real_id(t[2]) is None or _real_id(t[2]) in seen:
            continue
        seen.add(_real_id(t[2]))
        d = float(t[4].distance(lookup_m))
        if d <= NEARBY_RADIUS_M:
            info = _building_info(t[2], t[3])
            out.append({"outline_id": info["id"], "area_sqft": round(float(info["area_sqft"]), 1),
                        "distance_m": round(d, 1), "on_matched_parcel": any(t is o for o in ok)})
    out.sort(key=lambda r: (r["distance_m"], r["outline_id"]))
    return out[:NEARBY_MAX]


def _choose_outline(ok: list[tuple], point_m: Point | None) -> tuple:
    """The outline on the parcel for the caller's point: the one containing it, else the nearest, else the largest.

    ``ok`` rows are ``(intersection area, share inside the parcel, feature, polygon, projected polygon)``; with no
    point the largest overlap with the parcel wins (the old rule).
    """
    if point_m is None:
        return max(ok, key=lambda t: t[0])
    holding = [t for t in ok if t[4].contains(point_m)]
    if holding:
        return max(holding, key=lambda t: t[0])
    return min(ok, key=lambda t: t[4].distance(point_m))


def fetch_county(lat: float, lng: float, address: Address, *, point_given: bool = False,
                 building_outline_id: str | None = None) -> tuple[Footprint | None, list[Note], str | None]:
    """(footprint or None, notes for the footprint that replaces it, outage text or None).

    ``point_given``: ``lat``/``lng`` is the caller's rooftop point (not a street geocode): the parcel that contains it
    and the outline on that parcel that contains or is nearest to it are chosen (``match`` stays text based).
    ``building_outline_id``: use exactly that county outline (``match`` "given"; ``FootprintError`` when the layer
    has no such outline). The point is then taken from the outline itself.

    A matched parcel with no building outline is no longer fatal: it returns None plus a
    ``parcel_without_building`` note and the chain tries OpenStreetMap; a failing layer query does the same with
    a note. This link never raises for an outage.
    """
    if building_outline_id is not None:
        try:
            named = _outline_lookup(str(building_outline_id))
        except cache.NET_ERRORS as e:
            log.info("LA County outline lookup failed: %s", cache.describe_error(e))
            return None, [("source_unreachable", "LA County layer unreachable.")], "LA County layer unreachable"
        if named is None:
            raise FootprintError(f"The county building outline {str(building_outline_id)[:40]} was not found.")
        rp = named.representative_point()
        (lat, lng), point_given = (rp.y, rp.x), True
    if not (LA_BBOX[0] <= lat <= LA_BBOX[1] and LA_BBOX[2] <= lng <= LA_BBOX[3]):
        return None, [], None
    pq = {"f": "geojson", "geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
          "spatialRel": "esriSpatialRelIntersects", "distance": 60, "units": "esriSRUnit_Meter",
          "outFields": "*", "outSR": 4326, "returnGeometry": "true"}
    try:
        parcels = cache.fetch_json(PARCEL_URL, params=pq, check=_arcgis_check).get("features", [])
    except cache.NET_ERRORS as e:
        # An unreachable layer is NOT "outside the county": say so on whatever footprint replaces it.
        log.info("LA County parcel query failed: %s", cache.describe_error(e))
        return None, [("source_unreachable", "LA County layer unreachable; footprint from OpenStreetMap.")], "LA County layer unreachable"
    parcels = [f for f in parcels if f.get("geometry")]
    if not parcels:
        return None, [], None  # genuinely outside the county layer
    if building_outline_id is not None:  # the parcel is the one under the outline, never the one the text names
        under = [(shape(f["geometry"]).intersection(named).area, f) for f in parcels]
        area_under, parcel = max(under, key=lambda t: t[0])
        if area_under <= 0:
            raise FootprintError(f"The county building outline {str(building_outline_id)[:40]} is not on any parcel.")
        match = "given"
    else:
        parcel, match = pick_parcel(parcels, lat, lng, address, point_given=point_given)
    warnings: list[Note] = []
    if match != "exact" and building_outline_id is None:
        text = (f"Address {address.line1} has no exact parcel match; used parcel "
                f"{parcel['properties'].get('SitusAddress')} ({match} match).")
        warnings.append(("parcel_street_match", text))
    parcel_poly = as_polygon(parcel["geometry"])
    c = parcel_poly.centroid
    epsg = utm_epsg_for(c.x, c.y)
    parcel_m = project_geometry(parcel_poly, 4326, epsg)
    # WHY the parcel grown by the radius: ONE request answers both "which buildings are on the parcel" and "which
    # others stand within the radius of the point" (``nearby_buildings``, 0.5.1); a second query would cost a round trip
    # per measurement. The parcel rule below (overlap with the parcel) is applied to every row exactly as before.
    reach = project_geometry(parcel_m.buffer(NEARBY_RADIUS_M, 4).simplify(0.5), epsg, 4326)
    ring = list(reach.exterior.coords)
    if reach.exterior.is_ccw != parcel_poly.exterior.is_ccw:  # the winding the parcel's own ring had (the layer accepts it)
        ring.reverse()
    bq = {"f": "geojson", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
          "outSR": 4326, "returnGeometry": "true", "geometryType": "esriGeometryPolygon",
          "geometry": json.dumps({"rings": [[list(p) for p in ring]], "spatialReference": {"wkid": 4326}})}
    try:
        resp = cache.fetch_json(BUILDING_URL, method="POST", data=bq, check=_arcgis_check)
        capped = bool(resp.get("exceededTransferLimit") or (resp.get("properties") or {}).get("exceededTransferLimit"))
        if capped:  # the widened query hit the layer's record cap: answer from the parcel alone, list no neighbours
            log.info("LA County building query exceeded the transfer limit; parcel-only query")
            bq["geometry"] = json.dumps({"rings": _esri_rings(parcel_poly), "spatialReference": {"wkid": 4326}})
            resp = cache.fetch_json(BUILDING_URL, method="POST", data=bq, check=_arcgis_check)
        feats = resp.get("features", [])
    except cache.NET_ERRORS as e:
        log.info("LA County building query failed: %s", cache.describe_error(e))
        text = (f"The LA County building layer could not be queried ({cache.describe_error(e)}); "
                "footprint taken from another source.")
        return None, [*warnings, ("source_unreachable", text)], "LA County building layer unreachable"
    if capped:
        warnings.append(("other", "Buildings near the parcel were not listed: the county layer returned too many outlines."))
    lookup_m = project_geometry(Point(lng, lat), 4326, epsg)
    point_m = lookup_m if point_given else None
    scored = []
    for f in feats:
        if not f.get("geometry"):
            continue
        poly = as_polygon(f["geometry"])
        bm = project_geometry(poly, 4326, epsg)
        inter = bm.intersection(parcel_m).area
        scored.append((inter, inter / bm.area if bm.area else 0.0, f, poly, bm))
    # WHY overlap and not "intersects + largest": a big neighbour that merely touches the parcel edge
    # is returned by the intersects query and used to win on size.
    ok = [t for t in scored if t[1] >= MIN_PARCEL_OVERLAP]
    named_row = None
    if building_outline_id is not None:  # the caller's outline, exactly; the other buildings follow the usual rule
        named_row = next((t for t in scored if _real_id(t[2]) == str(building_outline_id)), None)
        if named_row is None:
            raise FootprintError(f"The county building outline {str(building_outline_id)[:40]} is not on the parcel "
                                 "that holds it.")
        ok = [named_row] + [t for t in ok if t is not named_row]
    if not ok:
        if match in ("exact", "street"):
            # The geocode point is on the street, so OSM may pick a building across it: say so on the result.
            text = ("The parcel matched but has no building outline in the county layer "
                    f"(parcel {parcel['properties'].get('AIN')}); footprint taken from another source.")
            warnings.append(("parcel_without_building", text))
        return None, warnings, None
    chosen = named_row or _choose_outline(ok, point_m)
    ok = [chosen] + sorted((t for t in ok if t is not chosen), key=lambda t: t[0], reverse=True)
    _, _, main_f, main, _ = ok[0]
    props = main_f["properties"]
    area = props.get("AREA")
    fp = Footprint(
        provider="lacounty_lariac_2020",
        id=_outline_id(main_f, main),
        polygon_wgs84=main,
        height_ft=float(props["HEIGHT"]) if props.get("HEIGHT") else None,
        area_sqft=float(area) if area else area_sqft(main),
        parcel_id=str(parcel["properties"].get("AIN")) if parcel["properties"].get("AIN") else None,
        other_buildings=[t[3] for t in ok[1:]], match=match, source="lariac",
        nearby=[] if capped else _nearby(scored, ok, ok[0], lookup_m),
        other_info=[_building_info(t[2], t[3]) for t in ok[1:]])
    if not _real_id(main_f):
        warnings.append(("other", "The county outline has no id; a geometry-based id was used, so it cannot be named later."))
    for code, text in warnings:
        fp.warn(code, text)
    return fp, [], None

