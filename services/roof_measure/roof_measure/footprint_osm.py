"""OpenStreetMap link of the footprint chain: hedged Overpass mirrors, then pick the real building.

WHY hedged: Overpass mirrors are often slow or shedding load. Asking all three at once with a short timeout
and a short server-side ``[timeout:25]`` ends the stage in about 12 s instead of three sequential 70 s waits.
"""

from __future__ import annotations

import contextvars
import functools
import logging
import os
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any

from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient

from . import cache
from .deadline import Deadline
from .footprint_types import Footprint, FootprintUnavailable, address_tokens, area_sqft
from .frame import FT_PER_M
from .geocode import Address

log = logging.getLogger(__name__)

DEFAULT_OVERPASS_URLS = ("https://overpass-api.de/api/interpreter",
                         "https://lz4.overpass-api.de/api/interpreter",
                         "https://z.overpass-api.de/api/interpreter")
OVERPASS_URLS = DEFAULT_OVERPASS_URLS  # kept for callers; use mirror_urls() for the env override
MIRROR_TIMEOUT_S = 45.0  # public instances took 30-37 s on a real query (D18)
MIN_OSM_SQFT = 400.0
MAX_OSM_CENTROID_M = 30.0
OSM_NOTE = "Footprint from OpenStreetMap; no parcel match or roof height from the county."


def _overpass_check(obj: dict) -> None:
    """Overpass reports timeouts and load shedding as a `remark` on a 200 response with no elements."""
    if isinstance(obj, dict) and obj.get("remark"):
        raise cache.BadResponse(f"Overpass remark: {str(obj['remark'])[:200]}")


def overpass_query(lat: float, lng: float) -> str:
    return f'[out:json][timeout:25];way["building"](around:40,{lat},{lng});out geom tags;'


def mirror_urls(env: dict[str, str] | None = None) -> tuple[str, ...]:
    """``ROOF_MEASURE_OVERPASS_URLS`` (comma separated) or the official instances."""
    raw = (os.environ if env is None else env).get("ROOF_MEASURE_OVERPASS_URLS", "")
    urls = tuple(u.strip() for u in raw.split(",") if u.strip())
    return urls or DEFAULT_OVERPASS_URLS


def fetch_overpass(lat: float, lng: float, deadline: Deadline | None = None,
                   urls: tuple[str, ...] | None = None) -> dict[str, Any]:
    """All mirrors in parallel at t=0; the first success wins and the rest are abandoned (plan D18).

    An error on one mirror (429, 502, 503, 504, down) never delays the others. Raises FootprintError
    ('could not be reached') when every mirror fails or the deadline passes. Every call carries the
    User-Agent ``cache.py`` sets.
    """
    urls = urls or mirror_urls()
    data = {"data": overpass_query(lat, lng)}
    timeout = deadline.timeout(MIRROR_TIMEOUT_S) if deadline else MIRROR_TIMEOUT_S
    pool = ThreadPoolExecutor(max_workers=len(urls), thread_name_prefix="overpass")
    ctx = contextvars.copy_context()
    futures = {pool.submit(ctx.copy().run, functools.partial(
        cache.fetch_json, u, method="POST", data=data, timeout=timeout, retries=0, check=_overpass_check)): u
        for u in urls}
    failures: list[str] = []
    pending = set(futures)
    try:
        while pending:
            left = deadline.remaining() if deadline else timeout + 1.0
            done, pending = wait(pending, timeout=min(left, timeout + 1.0), return_when=FIRST_COMPLETED)
            for f in done:
                try:
                    return f.result()
                except cache.NET_ERRORS as e:
                    log.info("Overpass %s failed: %s", cache.host_of(futures[f]), cache.describe_error(e))
                    failures.append(f"{cache.host_of(futures[f])}: {cache.describe_error(e)}")
            if not done:
                failures.append("timed out")
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    raise FootprintUnavailable("OpenStreetMap (Overpass) could not be reached, so no fallback footprint is "
                         "available: " + "; ".join(failures)[:300])


def parse_osm(payload: dict[str, Any], lat: float, lng: float, address: Address | None = None) -> Footprint | None:
    """Choose the building from an Overpass payload (split out so tests need no network)."""
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
            cands.append((el, poly, area_sqft(poly), d_m))
    if not cands:
        return None
    match = "nearest"
    num = address_tokens(address.line1)[0] if address else ""
    tagged = [c for c in cands if num and str(c[0].get("tags", {}).get("addr:housenumber", "")) == num]
    warn: list[tuple[str, str]] = []
    if tagged:
        pool, match = tagged, "exact"
    else:
        # WHY: the geocode point is in the street, so "nearest" picks a shed. Take the largest real building.
        pool = [c for c in cands if c[2] >= MIN_OSM_SQFT and c[3] <= MAX_OSM_CENTROID_M]
        if not pool:
            pool = sorted(cands, key=lambda c: c[3])[:1]
            warn.append(("other", "Only a small or distant OSM building was found; verify it is the right one."))
    el, main, area, _ = max(pool, key=lambda c: c[2])
    height = None
    m = re.match(r"\s*([\d.]+)", str(el.get("tags", {}).get("height", "")))
    if m:
        height = float(m.group(1)) * FT_PER_M
    fp = Footprint(provider="osm", id=str(el["id"]), polygon_wgs84=main, height_ft=height, area_sqft=area,
                   parcel_id=None, other_buildings=[c[1] for c in cands if c[0] is not el], match=match,
                   source="osm")
    for code, text in [*warn, ("footprint_osm", OSM_NOTE)]:
        fp.warn(code, text)
    return fp


def fetch_osm(lat: float, lng: float, address: Address | None = None,
              deadline: Deadline | None = None) -> Footprint | None:
    """OSM building near the point, or None when OSM has none; FootprintError when OSM is unreachable."""
    return parse_osm(fetch_overpass(lat, lng, deadline), lat, lng, address)
