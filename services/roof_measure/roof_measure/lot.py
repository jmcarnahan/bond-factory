"""Every building on the lot: measure the county's other outlines with the rule method and attach them to the envelope.

``measure(..., include_other_buildings=True)`` runs the usual pipeline for the main building (the largest outline on
the parcel), then ``add_other_buildings`` measures each other outline of at least ``MIN_AREA_SQFT`` with
``lidar_skeleton`` (no agent, no verifier) inside the same deadline. Nothing here runs unless asked, and a failing
second building never fails the first.

Frames: every building gets its own model frame (feet, origin at the south-west corner of its own bounding box) in the
SAME metric CRS as the main one, so north and the unit are shared and the only difference is the origin.
``offset_ft`` is that origin difference: ``[dx, dy]`` to add to a point of the second model to put it in the main
model's frame.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

from . import cache, errors
from .deadline import Deadline
from .frame import FT_PER_M

log = logging.getLogger(__name__)

MIN_AREA_SQFT = 120.0  # a smaller outline (a shed, a meter closet) is not worth a roof model
MIN_SHARE_S = 8.0  # less time than this for a building: skip it (and the ones after it) and say so
MAX_BUILDINGS = 6  # the largest few; a parcel of dozens of outlines must not eat the deadline
TIMEOUT = "timeout"
OK, PLANES_ONLY, FAILED = "ok", "planes_only", "failed"


@dataclass
class Candidate:
    """One other outline from the footprint source."""

    polygon_wgs84: Polygon
    provider: str
    id: str
    area_sqft: float


# ----------------------------------------------------------------------------- finding the buildings
def find_candidates(res: Any, address: str, lat_lng: tuple[float, float] | None, deadline: Deadline,
                    blocks_path: str | Path | None = None, pinned: bool = True) -> list[Candidate]:
    """The other outlines of the main building's footprint, largest first (``[]`` when there are none).

    Runs the footprint chain again for the same point: every request is in the fetch cache from the main run, so
    it is free. If the answer is not the building that was measured (a different id), nothing is returned.
    """
    if blocks_path or res.footprint_source not in ("lariac", "osm"):
        return []
    from . import footprint as fp_mod
    from .pipeline_stages import _locate

    try:
        lat, lng, parts, _ = _locate(address, lat_lng)
        chosen = ((getattr(res, "model", None) or {}).get("source") or {}).get("building") or {}
        fp = fp_mod.fetch_footprint(  # the same choice as the measurement: the caller's pin, or the outline they named
            lat, lng, parts, deadline=deadline, point_given=pinned and lat_lng is not None,
            building_outline_id=chosen.get("outline_id") if chosen.get("chosen_by") == "user" else None)
    except Exception as exc:  # noqa: BLE001 - the extra buildings are an addition, never a way to fail
        log.info("other buildings: footprint lookup failed (%s)", type(exc).__name__)
        return []
    meta = res.blockset.footprint_meta
    if fp.id != str(meta.get("id")) or fp.provider != meta.get("provider"):
        return []
    info = fp.other_info if len(fp.other_info) == len(fp.other_buildings) else [None] * len(fp.other_buildings)
    out = [Candidate(poly, fp.provider, (i or {}).get("id") or f"other{n}",
                     float((i or {}).get("area_sqft") or _area(poly)))
           for n, (poly, i) in enumerate(zip(fp.other_buildings, info, strict=True), 1)]
    return sorted(out, key=lambda c: -c.area_sqft)


def _area(poly: Polygon) -> float:
    from .footprint_types import area_sqft

    return area_sqft(poly)


# ----------------------------------------------------------------------------- measuring one building
def build_blocks(cand: Candidate, main_frame: dict[str, Any], address: dict[str, Any], out_path: Path) -> Any:
    """LiDAR blocks of one outline in a frame of the main frame's CRS; written to ``out_path`` and read back."""
    from . import blocks as blocks_mod
    from . import lidar
    from .classify import BlockSet
    from .frame import Frame, project_geometry

    epsg = int(main_frame["epsg"])
    fp_m = project_geometry(cand.polygon_wgs84, 4326, epsg)
    frame = Frame.from_footprint_m(fp_m, epsg)  # type: ignore[arg-type]
    points = lidar.fetch_for_footprint(fp_m, epsg)  # type: ignore[arg-type]
    meta = {"provider": cand.provider, "id": cand.id, "area_sqft": cand.area_sqft, "height_ft": None}
    bs = blocks_mod.segment_blocks(points, fp_m, frame, address=address, footprint_meta=meta)  # type: ignore[arg-type]
    bs.to_json(out_path)
    return BlockSet.load(out_path)


def offset_ft(main_frame: dict[str, Any], other_frame: dict[str, Any]) -> list[float]:
    """Where the other model's origin lies in the main model's frame, plan feet ``[dx (east), dy (north)]``."""
    if int(main_frame["epsg"]) != int(other_frame["epsg"]):
        raise ValueError("the two buildings are not in the same coordinate system")
    return [round((float(other_frame["x0_m"]) - float(main_frame["x0_m"])) * FT_PER_M, 2),
            round((float(other_frame["y0_m"]) - float(main_frame["y0_m"])) * FT_PER_M, 2)]


def _failed(index: int, cand: Candidate, code: str) -> dict[str, Any]:
    return {"index": index, "footprint": _fp_dict(cand), "offset_ft": None, "status": FAILED, "error_code": code,
            "model": None, "totals": None}


def _fp_dict(cand: Candidate) -> dict[str, Any]:
    return {"provider": cand.provider, "id": cand.id, "area_sqft": round(cand.area_sqft, 1)}


def measure_one(index: int, cand: Candidate, main_frame: dict[str, Any], address: dict[str, Any], out_dir: Path,
                deadline: Deadline, builder: Callable[..., Any] | None = None, engine: str = "blocks") -> dict[str, Any]:
    """The ``other_buildings`` entry of one outline; every failure becomes ``status`` ``failed`` plus a job code.
    ``engine="planes"`` measures it with the plane engine (the same engine as the main building)."""
    from .pipeline import run_pipeline

    work = out_dir / f"lot_{index}"
    try:
        work.mkdir(parents=True, exist_ok=True)
        if engine == "planes":
            from .pipeline_engine import run_planes_outline

            res = run_planes_outline(cand, main_frame, address, work, deadline)
            base = res.blockset
        else:
            with cache.deadline_scope(deadline):
                base = (builder or build_blocks)(cand, main_frame, address, work / "blocks.json")
            deadline.check("blocks")
            res = run_pipeline(address.get("formatted") or address.get("line1") or "lot building", work,
                               "lidar_skeleton", blocks_path=work / "blocks.json", deadline=deadline, verify=False,
                               render=False)
        env = res.envelope
        planes_only = bool((env["model"].get("source") or {}).get("planes_only"))
        entry = {"index": index, "footprint": _fp_dict(cand), "offset_ft": offset_ft(main_frame, base.frame),
                 "status": PLANES_ONLY if planes_only else OK, "error_code": None, "model": env["model"],
                 "totals": env["totals"]}
        json.dumps(entry, allow_nan=False)  # a NaN anywhere in this building fails this building, not the main result
        _lot_part(entry["totals"])  # ... as does a total the lot sums cannot use
        return entry
    except Exception as exc:  # noqa: BLE001 - one building failing is recorded, never fatal
        code = errors.code_for(exc)
        log.info("other building %d failed: %s", index, type(exc).__name__)
        return _failed(index, cand, code)


# ----------------------------------------------------------------------------- the envelope
def add_other_buildings(res: Any, *, address: str, lat_lng: tuple[float, float] | None, deadline: Deadline | None,
                        out_dir: str | Path, blocks_path: str | Path | None = None, pinned: bool = True,
                        finder: Callable[..., list[Candidate]] | None = None,
                        builder: Callable[..., Any] | None = None, engine: str = "blocks") -> None:
    """Measure the other buildings of ``res`` (a ``PipelineResult``) and add the envelope keys; no-op when none."""
    deadline = deadline or Deadline.after(10_000)
    try:
        cands = (finder or find_candidates)(res, address, lat_lng, deadline, blocks_path,
                                           **({} if finder else {"pinned": pinned}))
    except Exception as exc:  # noqa: BLE001 - a lookup bug must not fail the main result
        log.info("other buildings: lookup failed (%s)", type(exc).__name__)
        return
    cands = [c for c in cands if c.area_sqft >= MIN_AREA_SQFT][:MAX_BUILDINGS]
    if not cands:
        return
    main_frame = res.blockset.frame
    entries: list[dict[str, Any]] = []
    for n, cand in enumerate(cands, 1):
        share = deadline.remaining() / (len(cands) - n + 1)  # a fair share of what is left
        if share < MIN_SHARE_S:
            entries.extend(_failed(i, c, TIMEOUT) for i, c in enumerate(cands[n - 1:], n))
            break
        entries.append(measure_one(n, cand, main_frame, res.blockset.address, Path(out_dir), Deadline.after(share),
                                   builder, engine))
    try:
        _attach(res.envelope, entries)
    except Exception as exc:  # noqa: BLE001 - the lot is an addition: it never fails or pollutes the main result
        log.info("other buildings: not attached (%s)", type(exc).__name__)
        _warn(res.envelope, "the other buildings on the parcel could not be added; the lot totals are left out.")


def _warn(env: dict[str, Any], text: str) -> None:
    env["warnings"] = [*env.get("warnings", []), text[0].upper() + text[1:]]
    if "other" not in env.get("warning_codes", []):
        env["warning_codes"] = [*env.get("warning_codes", []), "other"]


def _lot_part(tot: Any) -> tuple[float, float, float]:
    """(area, squares, perimeter) of one building's totals; ValueError when one is missing or not finite."""
    area, squares = float(tot["area_sqft"]), float(tot["squares"])
    perim = float(tot.get("outline_perimeter_ft", tot.get("eave_ft", 0.0)))
    if not all(math.isfinite(v) for v in (area, squares, perim)):
        raise ValueError("non-finite building totals")
    return area, squares, perim


def _attach(env: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    """Add ``other_buildings`` and the lot totals. A building whose totals cannot be summed becomes ``failed``; the
    main totals are only written when every lot total is finite (else ValueError and nothing is written)."""
    entries = list(entries)
    for k, e in enumerate(entries):
        if e["status"] != FAILED:
            try:
                _lot_part(e["totals"])
            except (KeyError, TypeError, ValueError):
                entries[k] = {**e, "status": FAILED, "error_code": errors.code_for(ValueError()), "model": None,
                              "totals": None, "offset_ft": None}
    t = env["totals"]
    parts = [_lot_part(t), *[_lot_part(e["totals"]) for e in entries if e["status"] != FAILED]]
    lot = {"lot_buildings": len(parts), "lot_area_sqft": round(sum(p[0] for p in parts), 3),
           "lot_squares": round(sum(p[1] for p in parts), 3),
           "lot_outline_perimeter_ft": round(sum(p[2] for p in parts), 3)}
    if not all(math.isfinite(float(v)) for v in lot.values()):
        raise ValueError("non-finite lot totals")
    t.update(lot)
    env["other_buildings"] = entries
    lost = [e for e in entries if e["status"] == FAILED]
    if lost:
        _warn(env, f"{len(lost)} other building{'s' if len(lost) != 1 else ''} on the parcel could not be measured "
                   f"({', '.join(sorted({str(e['error_code']) for e in lost}))}); the lot totals leave "
                   f"{'it' if len(lost) == 1 else 'them'} out.")
