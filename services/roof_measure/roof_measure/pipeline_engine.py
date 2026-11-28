"""The pipeline: address -> footprint -> LiDAR -> plane engine -> model -> 0.2 envelope.

There is no fallback to another engine (a fallback would hide a failure): when the engine refuses or fails, the caller
gets an error code (``lidar_too_sparse``, ``no_footprint``, ``timeout``, ``measurement_failed``). No verifier runs: the
diagram comes straight from the measured planes and is labelled unverified.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .blockset import BlockSet
from .deadline import Deadline, DeadlineExceeded
from .envelope import build_envelope
from .lidar import MIN_ROOF_DENSITY, LidarError, LidarTooSparse
from .model import write_model
from .pipeline_notes import collect_warnings
from .pipeline_result import PipelineResult, no_verification
from .text import slug

log = logging.getLogger("roof_measure.pipeline_engine")

METHOD = "lidar_skeleton"  # the validated method name an engine result carries (see model.METHODS)
MIN_HAG_M = 1.5  # a return lower than this above local ground is a car, a bush or the ground
MAX_OVERHANG_M = 0.6  # roof returns kept this far past the footprint; the engine's data was cut the same way
CONTEXT_RING_M = 8.0  # the wider cloud handed to the engine's ring signal


def _warning_text(code: str, res: Any, low_slope_sqft: float = 0.0) -> str:
    q = res.quality
    return {"low_density": f"LiDAR density on the roof is low ({q.density} points/m2, under 6); lengths and pitch may be rough.",
            "outline_mismatch": "The roof points do not match the building outline closely; the outline may be a different "
                                "building or a different roof.",
            "poor_fit": "The measured planes fit the roof points poorly; the diagram may be rough.",
            "low_slope_confirm": f"About {low_slope_sqft:.0f} sq ft of the roof is close to flat (about 2/12): "
                                 "confirm the roof type at the site."}[code]


def engine_warnings(res: Any) -> list[tuple[str, str]]:
    """(code, text) for the verdict reasons the engine raised and for borderline low-slope facets."""
    out = [(c, _warning_text(c, res)) for c in res.quality.reasons if c in ("low_density", "outline_mismatch", "poor_fit")]
    low = float(res.totals.get("low_slope_confirm_sqft") or 0.0)
    if low > 0:
        out.append(("low_slope_confirm", _warning_text("low_slope_confirm", res, low)))
    return out


def measure_points(points: Any, fp_m: Any, frame: Any, base: BlockSet, *, deadline: Deadline,
                   params: Any = None, parcel_match: str | None = None) -> tuple[Any, float, dict[str, Any]]:
    """Run the engine on one building. Returns ``(EngineResult, ground_z_m, lidar meta)``.

    ``points`` is the LiDAR ``PointCloud`` in ``frame.epsg``, ``fp_m`` the footprint in the same CRS. Raises ``LidarTooSparse`` under 4 points/m2 on the roof, ``DeadlineExceeded``, ``FootprintError``.
    """
    import numpy as np
    from shapely import affinity
    from shapely import contains_xy as inside
    from shapely.geometry.polygon import orient

    from .engine import measure_roof
    from .engine.errors import EngineTimeout
    from .engine.params import DEFAULT
    from .engine.points import roof_points
    from .footprint_types import FootprintError

    fpl = orient(affinity.translate(fp_m, -frame.x0_m, -frame.y0_m), 1.0)
    xyzc = np.column_stack([np.asarray(points.x) - frame.x0_m, np.asarray(points.y) - frame.y0_m,
                            np.asarray(points.z), np.asarray(points.classification)])
    # the same reach the regression data uses: min(0.6 m, 8% of the footprint's side). A wider reach
    # (an earlier 1.3 m) pulled trees and the neighbour's wall into the planes and wrecked roofs the harness measured fine.
    reach = min(MAX_OVERHANG_M, 0.08 * float(np.sqrt(fpl.area)))
    rp = roof_points(xyzc, fpl, overhang_m=reach, min_height_m=MIN_HAG_M)
    project, year = points.meta.get("project"), points.meta.get("year")
    if rp.density < MIN_ROOF_DENSITY:
        raise LidarTooSparse(project, year, rp.density, MIN_ROOF_DENSITY)
    keep = inside(fpl.buffer(CONTEXT_RING_M), xyzc[:, 0], xyzc[:, 1])
    meta = base.footprint_meta or {}
    try:
        res = measure_roof(rp, fpl, params=params or DEFAULT, deadline=deadline.at,
                           outline_source=str(meta.get("provider") or ""), parcel_match=parcel_match,
                           context=xyzc[keep])
    except EngineTimeout as exc:
        raise DeadlineExceeded("model") from exc
    if res.refused:
        verdict = res.quality.verdict
        if verdict == "lidar_too_sparse":
            raise LidarTooSparse(project, year, float(res.quality.density if res.quality.density is not None else rp.density),
                                 MIN_ROOF_DENSITY)
        if verdict == "bad_footprint":
            raise FootprintError("The building outline is not usable for the plane engine.")
        raise LidarError(f"The LiDAR returns over this roof are not usable ({verdict}).")
    acq = None
    try:
        from .lidar import acquired_range

        acq = acquired_range(np.asarray(points.gps_time)[rp.on_roof]) or points.meta.get("acquired")
    except Exception:  # noqa: BLE001 - the acquisition range is decoration, never a way to fail
        acq = points.meta.get("acquired")
    dens = res.quality.density if res.quality.density is not None else rp.density  # the engine's own roof density
    lidar_meta = {"project": project, "acquired": acq, "year": year, "points_on_roof": rp.n_on_roof,
                  "density_per_m2": round(float(dens), 1), "ground_z_m": round(rp.ground_z, 2), "epsg": frame.epsg}
    return res, rp.ground_z, lidar_meta


def build_result(res: Any, ground_z: float, lidar_meta: dict[str, Any], base: BlockSet, fpinfo: dict[str, Any],
                 out: Path, tag: str, params: Any = None, extra_notes: list[str] | None = None,
                 hints: dict[str, Any] | None = None) -> Any:
    """Model, assessment and envelope of an engine result; writes ``<tag>_model.json`` and ``<tag>_engine.json``."""
    import json

    from .engine.adapter import engine_model
    from .quality import assess_engine

    base.lidar = lidar_meta
    model = engine_model(res, base, ground_z, {"method": METHOD}, params or _default_params(), extra_notes)
    if fpinfo.get("building"):  # contract 0.4: which building was measured
        model.setdefault("source", {})["building"] = fpinfo["building"]
    if hints:  # the answers this measurement was made with (present only when given)
        model.setdefault("source", {})["hints"] = dict(hints)
    # the LLM verifier never runs on the engine path: it only checks edge-sum arithmetic and
    # passed a wrong roof; the engine's own signals and verdict replace it. ``skipped`` tells readers it was not tried.
    verification = {**no_verification(model, "The diagram comes straight from the measured planes; the verifier "
                                              "does not run on it."), "skipped": "engine"}
    density = lidar_meta["density_per_m2"]
    warnings, codes = collect_warnings(model, fpinfo, density, engine_warnings(res))
    assessment = assess_engine(res, model, codes)
    envelope = build_envelope(model, method_used=METHOD, footprint_source=fpinfo["source"], verification=verification,
                              warnings=warnings, warning_codes=codes, density_pts_m2=density, assessment=assessment)
    if fpinfo.get("nearby_buildings") is not None:  # 0.5.1: from the county outline query already made; absent elsewhere
        envelope["nearby_buildings"] = list(fpinfo["nearby_buildings"])
    out.mkdir(parents=True, exist_ok=True)
    paths = {"model": out / f"{tag}_model.json", "engine": out / f"{tag}_engine.json"}
    write_model(model, paths["model"])  # validated again: the file carries the quality and planes keys too
    paths["engine"].write_text(json.dumps(res.to_result_json(tag)))
    return PipelineResult(model=model, blockset=base, paths=paths, method_used=METHOD,
                          footprint_source=fpinfo["source"], verification=envelope["verification"], envelope=envelope,
                          density_pts_m2=density, transient=bool(fpinfo.get("transient")))


def _default_params() -> Any:
    from .engine.params import DEFAULT

    return DEFAULT


def run_planes(address: str, out_dir: str | Path, *, deadline: Deadline | None, lat_lng: tuple[float, float] | None,
               on_stage: Callable[[str], None], building_outline_id: str | None = None, pinned: bool = True,
               params: Any = None, points_path: str | Path | None = None,
               hints: dict[str, Any] | None = None) -> Any:
    """The whole pipeline for one address with the plane engine (``run_pipeline``)."""
    from . import cache
    from .pipeline_stages import _stage_points, _stage_points_dir

    deadline = deadline or Deadline.after(10_000)
    started = time.monotonic()
    if points_path:  # offline: a house folder replaces geocoder, footprint chain and LiDAR (the test hook of the engine)
        base, fp_m, frame, points = _stage_points_dir(points_path, address)
    else:
        with cache.deadline_scope(deadline):
            base, fp_m, frame, points = _stage_points(address, lat_lng, deadline, on_stage, building_outline_id, pinned)
    if not base.address.get("formatted"):
        base.address = {"line1": address, "city": "", "state": "", "zip": "", "formatted": address}
    fpinfo = base.extra.pop("_fp")
    deadline.check("model")
    on_stage("model")
    res, ground_z, lidar_meta = measure_points(points, fp_m, frame, base, deadline=deadline, params=params,
                                               parcel_match=fpinfo.get("match"))
    result = build_result(res, ground_z, lidar_meta, base, fpinfo, Path(out_dir), slug(address), params, hints=hints)
    log.info("planes pipeline done verdict=%s facets=%d ms=%d", res.quality.verdict, len(res.facets),
             int((time.monotonic() - started) * 1000))
    return result


def run_planes_outline(cand: Any, main_frame: dict[str, Any], address: dict[str, Any], work: Path,
                       deadline: Deadline, params: Any = None) -> Any:
    """One other building of the lot (``lot.measure_one``): its own frame in the main frame's CRS, the engine on it."""
    from . import cache, lidar
    from .frame import Frame, project_geometry

    epsg = int(main_frame["epsg"])
    fp_m = project_geometry(cand.polygon_wgs84, 4326, epsg)
    frame = Frame.from_footprint_m(fp_m, epsg)
    with cache.deadline_scope(deadline):
        points = lidar.fetch_for_footprint(fp_m, epsg)
    deadline.check("model")
    base = BlockSet(address=address, origin={"lat": frame.origin_lat, "lng": frame.origin_lng},
                    frame={"epsg": epsg, "x0_m": frame.x0_m, "y0_m": frame.y0_m}, footprint_ft=[],
                    footprint_meta={"provider": cand.provider, "id": cand.id, "area_sqft": cand.area_sqft,
                                    "height_ft": None})
    fpinfo = {"source": "lariac" if cand.provider.startswith("lacounty") else "osm", "warnings": [], "codes": [],
              "other_buildings": 0}
    res, ground_z, lidar_meta = measure_points(points, fp_m, frame, base, deadline=deadline, params=params)
    return build_result(res, ground_z, lidar_meta, base, fpinfo, work, slug(address.get("formatted") or "lot"), params)
