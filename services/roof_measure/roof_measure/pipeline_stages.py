"""Data stages of the pipeline: geocode, footprint chain, LiDAR, blocks. Imported lazily by ``pipeline``."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import config
from .classify import BlockSet
from .config import SOLAR_KEY_ENV  # noqa: F401  (re-exported: tests and pipeline import it from here)
from .deadline import Deadline


class PipelineError(RuntimeError):
    """A stage failed in a way the user can act on (message is for humans)."""


def parse_address(text: str) -> Any:
    """Best-effort ``Address`` from a one-line label such as ``100 Example Ave, Sampletown, CA 90000``."""
    from .geocode import Address

    bits = [b.strip() for b in text.split(",")]
    tail = (bits[2] if len(bits) > 2 else "").split()
    state = tail[0] if tail else ""
    zip_ = tail[1] if len(tail) > 1 else (bits[3] if len(bits) > 3 else "")
    return Address(bits[0], bits[1] if len(bits) > 1 else "", state, zip_)


# ----------------------------------------------------------------------------- data stages
def _locate(address: str, lat_lng: tuple[float, float] | None) -> tuple[float, float, Any, str]:
    from . import geocode

    if lat_lng is not None:
        return lat_lng[0], lat_lng[1], parse_address(address), address
    g = geocode.geocode(address)
    return g.lat, g.lng, g.parts, g.formatted


def _footprint_info(fp: Any) -> dict[str, Any]:
    return {"source": fp.source, "warnings": list(fp.warnings), "codes": list(fp.warning_codes),
            "other_buildings": len(fp.other_buildings), "transient": fp.transient}


def _address_dict(parts: Any, formatted: str) -> dict[str, str]:
    return {"line1": parts.line1, "city": parts.city, "state": parts.state, "zip": parts.zip, "formatted": formatted}


def _stage_footprint(address: str, lat_lng: tuple[float, float] | None, deadline: Deadline,
                     on_stage: Callable[[str], None]) -> BlockSet:
    """Geocode + footprint -> an empty block set (footprint only)."""
    import numpy as np
    from shapely.geometry import Polygon

    from . import footprint as fp_mod
    from . import frame as frame_mod

    on_stage("geocode")
    lat, lng, parts, formatted = _locate(address, lat_lng)
    deadline.check("footprint")
    on_stage("footprint")
    fp = fp_mod.fetch_footprint(lat, lng, parts, deadline=deadline)
    frame, fp_m = frame_mod.Frame.for_footprint(fp.polygon_wgs84)
    ring = [tuple(p) for p in frame.to_ft(np.array(fp_m.exterior.coords))][:-1]
    if not Polygon(ring).exterior.is_ccw:
        ring = ring[::-1]
    bs = BlockSet(address=_address_dict(parts, formatted), origin={"lat": frame.origin_lat, "lng": frame.origin_lng},
                  frame={"epsg": frame.epsg, "x0_m": frame.x0_m, "y0_m": frame.y0_m}, footprint_ft=ring,
                  footprint_meta={"provider": fp.provider, "id": fp.id, "area_sqft": fp.area_sqft,
                                  "height_ft": fp.height_ft})
    bs.extra["_geo"] = {"lat": lat, "lng": lng}
    bs.extra["_fp"] = _footprint_info(fp)
    return bs


def _stage_blocks(address: str, out_dir: Path, tag: str, lat_lng: tuple[float, float] | None, deadline: Deadline,
                  on_stage: Callable[[str], None]) -> BlockSet:
    """Full data stage for the LiDAR methods; the blocks JSON is written then read back."""
    from . import blocks as blocks_mod
    from . import footprint as fp_mod
    from . import frame as frame_mod
    from . import lidar

    on_stage("geocode")
    lat, lng, parts, formatted = _locate(address, lat_lng)
    deadline.check("footprint")
    on_stage("footprint")
    fp = fp_mod.fetch_footprint(lat, lng, parts, deadline=deadline)
    frame, fp_m = frame_mod.Frame.for_footprint(fp.polygon_wgs84)
    deadline.check("lidar")
    on_stage("lidar")
    points = lidar.fetch_for_footprint(fp_m, frame.epsg)
    deadline.check("blocks")
    on_stage("blocks")
    meta = {"provider": fp.provider, "id": fp.id, "area_sqft": fp.area_sqft, "height_ft": fp.height_ft}
    blockset = blocks_mod.segment_blocks(points, fp_m, frame, address=_address_dict(parts, formatted),
                                         footprint_meta=meta)
    path = out_dir / f"{tag}_blocks.json"
    blockset.to_json(path)
    base = BlockSet.load(path)
    base.extra["_fp"] = _footprint_info(fp)
    return base


def _solar_key() -> str:
    key = config.solar_key()
    if key:
        return key
    raise PipelineError("The live Solar API needs a key in GOOGLE_SOLAR_API_KEY (and the API enabled on the "
                        "project). Use --solar-fixture for the synthetic fixture.")
