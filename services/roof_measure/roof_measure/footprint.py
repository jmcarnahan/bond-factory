"""Building footprint for a point: the chain of sources (plan D6) and the shared value types.

Order: LA County parcel + LARIAC outline (``lariac``) -> OpenStreetMap (``osm``) -> Google Solar segment hull
(``solar``, only with a key) -> LiDAR hull (``lidar_hull``). Each link lives in its own module; ``Footprint.source``
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
from .footprint_solar import fetch_solar, solar_key
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
STAGE_CAP_S = FOOTPRINT_STAGE_S  # old name
_area_sqft = area_sqft  # old private names, kept for existing callers
_as_polygon = as_polygon
_tokens = address_tokens


def _with_notes(fp: Footprint | None, notes: list[tuple[str, str]]) -> Footprint | None:
    """Put the county link's notes (weak match, parcel without building) in front of the replacement's own."""
    if fp is not None and notes:
        fp.warnings[:0] = [text for _, text in notes]
        fp.warning_codes[:0] = [code for code, _ in notes]
    return fp


def fetch_footprint(lat: float, lng: float, address: Address, *, deadline: Deadline | None = None,
                    use_solar: bool = True, use_hull: bool = True) -> Footprint:
    """First building found by the chain; ``FootprintError`` (or ``AmbiguousBuilding``) when none has one."""
    cap = config.footprint_stage_s() or FOOTPRINT_STAGE_S
    stage = Deadline.after(min(cap, deadline.remaining())) if deadline else Deadline.after(cap)
    fp, notes, unreachable = fetch_county(lat, lng, address)  # unreachable: first link that could not be reached
    if fp is not None:
        return fp
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
    # An unreachable or empty link is a skip, never the end of the chain: the stage cap bounds OSM and Solar only,
    # and the LiDAR hull still gets the job's own remaining time.
    if fp is None and use_solar and (key := solar_key()) and not stage.expired():
        try:
            fp = _with_notes(fetch_solar(lat, lng, key, stage), notes)
        except FootprintUnavailable as exc:
            down(str(exc), "Google Solar")
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
