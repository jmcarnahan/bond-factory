"""Building footprint for a point: the chain of sources (plan D6) and the shared value types.

Order: LA County parcel + LARIAC outline (``lariac``) -> OpenStreetMap (``osm``) -> LiDAR hull
(``lidar_hull``). Each link lives in its own module; ``Footprint.source``
records which one answered. A parcel that matched but has no building outline no longer stops the chain.
The footprint stage as a whole is capped at ``FOOTPRINT_STAGE_S`` seconds (env ``ROOF_MEASURE_FOOTPRINT_S``).
"""

from __future__ import annotations

import logging
import os

from . import config
from .deadline import Deadline
from .footprint_county import (  # noqa: F401  (re-exported: tests and callers import these from here)
    BUILDING_URL,
    PARCEL_URL,
    _arcgis_check,
    fetch_county,
    pick_parcel,
    score_parcel,
)
from .footprint_hull import fetch_hull
from .footprint_osm import OVERPASS_URLS, fetch_osm, mirror_urls  # noqa: F401
from .footprint_types import (  # noqa: F401
    SQFT_PER_M2,
    AmbiguousBuilding,
    Footprint,
    FootprintError,
    FootprintUnavailable,
    address_tokens,
    area_sqft,
    as_polygon,
)
from .geocode import Address

log = logging.getLogger(__name__)

FOOTPRINT_STAGE_S = float(os.environ.get("ROOF_MEASURE_FOOTPRINT_S") or 60.0)  # footprint stage cap (D18)


def _with_notes(fp: Footprint | None, notes: list[tuple[str, str]]) -> Footprint | None:
    """Put the county link's notes (weak match, parcel without building) in front of the replacement's own."""
    if fp is not None and notes:
        fp.warnings[:0] = [text for _, text in notes]
        fp.warning_codes[:0] = [code for code, _ in notes]
    return fp


def fetch_footprint(lat: float, lng: float, address: Address, *, deadline: Deadline | None = None,
                    use_hull: bool = True, point_given: bool = False,
                    building_outline_id: str | None = None) -> Footprint:
    """First building found by the chain; ``FootprintError`` (or ``AmbiguousBuilding``) when none has one.

    ``point_given``: the point is the caller's rooftop pin (the county link then picks the parcel and outline that
    hold it). ``building_outline_id``: exactly that county outline or an error: the chain never substitutes another
    building for the one the caller chose."""
    cap = config.footprint_stage_s() or FOOTPRINT_STAGE_S
    stage = Deadline.after(min(cap, deadline.remaining())) if deadline else Deadline.after(cap)
    county_kw = {"point_given": True} if point_given else {}
    if building_outline_id is not None:
        county_kw["building_outline_id"] = building_outline_id
    fp, notes, unreachable = fetch_county(lat, lng, address, **county_kw)  # unreachable: first link not reached
    if fp is not None:
        return fp
    if building_outline_id is not None:
        if unreachable:
            raise FootprintUnavailable(unreachable[:300])
        raise FootprintError("The county building outline was not found.")
    hull_reason = ""

    def down(text: str, what: str) -> None:
        nonlocal unreachable, notes
        unreachable = unreachable or text
        notes = [*notes, ("source_unreachable", f"{what} could not be reached; footprint taken from another source.")]

    try:
        fp = _with_notes(fetch_osm(lat, lng, address, stage), notes)
    except FootprintError as exc:
        log.info("OSM link failed: %s", type(exc).__name__)
        down(str(exc), "OpenStreetMap")
    # An unreachable or empty link is a skip, never the end of the chain: the stage cap bounds OSM only,
    # and the LiDAR hull still gets the job's own remaining time.
    if fp is None and use_hull:
        if deadline:
            deadline.check("footprint")
        try:
            fp = _with_notes(fetch_hull(lat, lng, deadline), notes)
        except AmbiguousBuilding:
            raise
        except FootprintError as exc:
            log.info("LiDAR hull link failed: %s", type(exc).__name__)
            hull_reason = str(exc)
            if isinstance(exc, FootprintUnavailable):
                unreachable = unreachable or str(exc)
    if fp is None:
        if unreachable:  # every link failed and at least one was unreachable: retryable
            detail = f" LiDAR hull: {hull_reason}" if hull_reason else ""
            raise FootprintUnavailable((unreachable + detail)[:300])
        raise FootprintError(f"No building footprint found near {address.line1}, {address.city}. "
                             "LA County, OpenStreetMap and the LiDAR have nothing within 60 m.")
    fp.transient = unreachable is not None  # the answer came from a fallback because something was down
    return fp
