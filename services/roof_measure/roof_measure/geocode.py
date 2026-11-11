"""Address -> lat/lng with the keyless US Census geocoder.

WHY Census: no API key, authoritative for US street ranges. Its point lies on the street
centreline (about 17 ft outside the parcel), so callers must never do point-in-polygon on it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import cache

log = logging.getLogger(__name__)
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


class GeocodeError(RuntimeError):
    """No usable geocode for the address."""


class GeocodeUnavailable(GeocodeError):
    """The geocoder could not be reached: retryable, not 'no match'."""


@dataclass(frozen=True)
class Address:
    line1: str
    city: str
    state: str
    zip: str


@dataclass(frozen=True)
class Geocoded:
    lat: float
    lng: float
    formatted: str
    parts: Address


def parse_census(payload: dict, query: str) -> Geocoded:
    """Parse a Census `onelineaddress` JSON response (split out so tests need no network)."""
    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        raise GeocodeError(f"The Census geocoder found no match for '{query}'. "
                           "Check the street number, city and ZIP.")
    m = matches[0]
    formatted = m["matchedAddress"]
    bits = [b.strip() for b in formatted.split(",")]
    comp = m.get("addressComponents", {})
    line1 = bits[0].title() if bits else query
    city = (comp.get("city") or (bits[1] if len(bits) > 1 else "")).title()
    state = comp.get("state") or (bits[2] if len(bits) > 2 else "")
    zip_ = comp.get("zip") or (bits[3] if len(bits) > 3 else "")
    return Geocoded(lat=float(m["coordinates"]["y"]), lng=float(m["coordinates"]["x"]),
                    formatted=formatted, parts=Address(line1, city, state, zip_))


def geocode(address: str) -> Geocoded:
    """Geocode a one-line US address; raises `GeocodeError` with a human message on no match."""
    params = {"address": address, "benchmark": "Public_AR_Current", "format": "json"}
    try:
        payload = cache.fetch_json(CENSUS_URL, params=params, max_age_s=30 * cache.DAY, timeout=30)
    except cache.NET_ERRORS as e:  # network or HTTP failure
        raise GeocodeUnavailable(f"The Census geocoder could not be reached ({cache.describe_error(e)}).") from e
    return parse_census(payload, address)
