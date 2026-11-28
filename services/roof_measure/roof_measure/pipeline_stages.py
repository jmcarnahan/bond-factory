"""Data stages of the pipeline: geocode, footprint chain, LiDAR. Each stage reports itself through ``on_stage`` and checks the deadline before it starts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .blockset import BlockSet
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
    c = fp.polygon_wgs84.representative_point()  # always inside the outline (a centroid can miss an L or U shape)
    return {"source": fp.source, "warnings": list(fp.warnings), "codes": list(fp.warning_codes),
            "other_buildings": len(fp.other_buildings), "transient": fp.transient,
            # county outlines within 60 m of the lookup point (envelope ``nearby_buildings``); None for any other source
            "nearby_buildings": list(getattr(fp, "nearby", None) or []) if fp.source == "lariac" else None,
            # which building was measured (contract 0.4 ``model.source.building``); the match only means something for
            # a county parcel, so other sources carry none
            "match": fp.match if fp.source == "lariac" else None,
            "building": {"parcel_id": fp.parcel_id, "outline_id": fp.id,
                         "outline_centroid": [round(c.y, 7), round(c.x, 7)],
                         "chosen_by": "user" if fp.match == "given" else "auto"}}


def _address_dict(parts: Any, formatted: str) -> dict[str, str]:
    return {"line1": parts.line1, "city": parts.city, "state": parts.state, "zip": parts.zip, "formatted": formatted}


def _stage_points(address: str, lat_lng: tuple[float, float] | None, deadline: Deadline,
                  on_stage: Callable[[str], None], outline_id: str | None = None, pinned: bool = True) -> tuple[Any, ...]:
    """Data stage of the plane engine: ``(base, fp_m, frame, points)``. ``base`` is a footprint-only ``BlockSet``
    (address, origin, frame, footprint ring) with the footprint info in ``extra['_fp']``."""
    import numpy as np
    from shapely.geometry import Polygon

    from . import footprint as fp_mod
    from . import frame as frame_mod
    from . import lidar

    on_stage("geocode")
    lat, lng, parts, formatted = _locate(address, lat_lng)
    deadline.check("footprint")
    on_stage("footprint")
    fp = fp_mod.fetch_footprint(lat, lng, parts, deadline=deadline, building_outline_id=outline_id,
                                point_given=pinned and lat_lng is not None)
    frame, fp_m = frame_mod.Frame.for_footprint(fp.polygon_wgs84)
    deadline.check("lidar")
    on_stage("lidar")
    points = lidar.fetch_for_footprint(fp_m, frame.epsg)
    ring = [tuple(p) for p in frame.to_ft(np.array(fp_m.exterior.coords))][:-1]
    if not Polygon(ring).exterior.is_ccw:
        ring = ring[::-1]
    base = BlockSet(address=_address_dict(parts, formatted), origin={"lat": frame.origin_lat, "lng": frame.origin_lng},
                    frame={"epsg": frame.epsg, "x0_m": frame.x0_m, "y0_m": frame.y0_m}, footprint_ft=ring,
                    footprint_meta={"provider": fp.provider, "id": fp.id, "area_sqft": fp.area_sqft,
                                    "height_ft": fp.height_ft})
    base.extra["_fp"] = _footprint_info(fp)
    return base, fp_m, frame, points


def _stage_points_dir(house_dir: str | Path, address: str) -> tuple[Any, ...]:
    """Offline data stage of the plane engine: ``(base, fp_m, frame, points)`` read from a regression-set house folder
    (``points_wide.npy`` x, y, z, ASPRS class in a local metric frame with z absolute, ``footprint.json``,
    ``meta.json`` with ``frame`` {crs_epsg, x0_m, y0_m}, ``outline_source``, ``parcel_match``). The folder's local frame
    is moved back into its CRS so the rest of the pipeline sees what the live fetch gives."""
    import json

    import numpy as np
    from shapely import affinity
    from shapely.geometry import Polygon

    from . import frame as frame_mod
    from .lidar import PointCloud

    d = Path(house_dir)
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").is_file() else {}
    fm = meta.get("frame") or {}
    epsg, x0, y0 = int(fm.get("crs_epsg") or 32611), float(fm.get("x0_m") or 0.0), float(fm.get("y0_m") or 0.0)
    wide = np.load(d / "points_wide.npy").astype(float).reshape(-1, 4)
    fp_m = affinity.translate(Polygon(json.loads((d / "footprint.json").read_text())["polygon"]), x0, y0)
    frame = frame_mod.Frame.from_footprint_m(fp_m, epsg)
    lid = meta.get("lidar") or {}
    points = PointCloud(wide[:, 0] + x0, wide[:, 1] + y0, wide[:, 2], wide[:, 3].astype(np.uint8), np.zeros(len(wide)),
                        {"project": lid.get("project"), "year": lid.get("year"), "acquired": lid.get("acquired"),
                         "epsg": epsg})
    src = str(meta.get("outline_source") or "")
    county = "county" in src.lower() or "lariac" in src.lower()
    ring = [tuple(p) for p in frame.to_ft(np.array(fp_m.exterior.coords))][:-1]
    if not Polygon(ring).exterior.is_ccw:
        ring = ring[::-1]
    base = BlockSet(address={"line1": address, "city": "", "state": "", "zip": "", "formatted": address},
                    origin={"lat": frame.origin_lat, "lng": frame.origin_lng},
                    frame={"epsg": epsg, "x0_m": frame.x0_m, "y0_m": frame.y0_m}, footprint_ft=ring,
                    footprint_meta={"provider": "lacounty_lariac_2020" if county else (src or "osm"), "id": d.name,
                                    "area_sqft": fp_m.area * 10.7639, "height_ft": None})
    base.extra["_fp"] = {"source": "lariac" if county else "osm", "warnings": [], "codes": [], "other_buildings": 0,
                         "match": meta.get("parcel_match"), "building": None}
    return base, fp_m, frame, points
