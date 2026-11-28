"""EngineResult -> the library's roof model (``bond.roof_model/0.1``, contract 0.4 additions) and envelope totals.

WHY the model dict is built here and not by ``planes_model.model_from_planes``: that function re-types every edge from
plane heights (the engine has already typed them, once, in ``engine.edges``: a second typer would disagree), forces a
facet under 0.5/12 to pitch 0, rejects nothing it can fix but cannot carry ``roof_type``, ``level_change`` or the
engine's own ``jump_ft``, and imports the skeleton path. Building the same shape directly (one ``shed`` or ``flat``
block per facet, like ``model_from_planes``) takes fewer special cases; ``model.validate`` then checks the result.

Units: the engine works in metres in a local metric frame whose origin is the model's origin, so every x, y here is
``metres / 0.3048`` and every height is ``(z - ground_z) / 0.3048`` (feet above ground, as ``model.planes`` has them).
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from ..model import SCHEMA, ModelError, _totals, origin_of, validate
from .edges import edge_diagnostics
from .params import DEFAULT, EngineParams
from .types import EngineResult, Facet

FT = 1 / 0.3048
FLAT_KIND_RISE = 0.5  # contract 0.2: ``kind`` is flat under 0.5/12 (``roof_type`` cuts at 2.0/12)
MIN_ANGLE_DEG = 10.0  # model.validate rejects a facet corner sharper than this
SOURCE_METHOD = "lidar_skeleton"  # a validated METHODS value; a deliberate rename is a phase 3 job
COST_KEYS = ("planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "ridge_cap_ridge_hip_ft",
             "roofing_pitched_sqft", "roofing_flat_sqft", "roofing_pitched_squares", "roofing_flat_squares",
             "low_slope_confirm_sqft", "area_sqft_wall_line", "outline_perimeter_wall_ft", "overhang_ft_median",
             "flat_edge_ft", "level_change_ft", "complexity")
AREA_TOL_SQFT = 0.5  # the priced area may not leave [wall line, drawn] by more than this (rounding)


def _ring_ft(poly: Polygon) -> list[tuple[float, float]]:
    """Counter-clockwise open ring in feet, with repeated vertices removed."""
    ring = [(x * FT, y * FT) for x, y in poly.exterior.coords][:-1]
    out: list[tuple[float, float]] = []
    for pt in ring:
        if not out or math.dist(out[-1], pt) > 1e-6:
            out.append(pt)
    if len(out) > 1 and math.dist(out[0], out[-1]) < 1e-6:
        out.pop()
    if not Polygon(out).exterior.is_ccw:
        out.reverse()
    return out


def _corner_deg(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    l1, l2 = math.hypot(*v1), math.hypot(*v2)
    if l1 < 1e-9 or l2 < 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))))


def despike(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop the sharpest vertex while a corner is under 10 degrees (``model.validate`` refuses such a facet). The
    engine's partition seldom produces one; when it does the tip is a sliver a few inches long."""
    ring = list(ring)
    while len(ring) > 3:
        angs = [_corner_deg(ring[i - 1], ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
        worst = min(range(len(ring)), key=lambda i: angs[i])
        if angs[worst] >= MIN_ANGLE_DEG + 0.25:
            break
        del ring[worst]
    return ring


def plane_eq_ft(f: Facet, ground_z_m: float) -> list[float]:
    """``z = a x + b y + c`` with x, y in feet and z in feet above ground (the equation ``model.planes`` carries)."""
    a, b, c = f.plane
    return [round(a, 5), round(b, 5), round((c - ground_z_m) * FT, 3)]


def _eave_height_ft(f: Facet, ring: list[tuple[float, float]], ground_z_m: float) -> float:
    eq = plane_eq_ft(f, ground_z_m)
    return max(0.0, min(eq[0] * x + eq[1] * y + eq[2] for x, y in ring))


def _facet_dicts(res: EngineResult, ground_z_m: float) -> tuple[list[dict], list[dict], set[str]]:
    """(facets, blocks, kept ids). A facet whose polygon collapses (area under 0.5 sq ft) is dropped."""
    facets, blocks, kept = [], [], set()
    k = 0
    for f in res.facets:
        ring = despike(_ring_ft(f.polygon))
        poly = Polygon(ring)
        if len(ring) < 3 or not poly.is_valid or poly.area < AREA_TOL_SQFT:
            continue
        k += 1
        kept.add(f.id)
        flat_kind = f.pitch_rise < FLAT_KIND_RISE
        pitch = 0.0 if flat_kind else float(f.pitch_rise)
        area = poly.area
        pts = [[x, y] for x, y in ring]
        facets.append({
            "id": f.id, "block": f"b{k}", "kind": "flat" if flat_kind else "sloped", "polygon": pts,
            "pitch_rise": pitch, "aspect_deg": None if flat_kind else float(f.aspect_deg),
            "plan_area_sqft": area, "area_sqft": area * math.sqrt(1 + (pitch / 12) ** 2),
            "roof_type": f.roof_type, "pitch_fit": f.pitch_fit, "pitch_sigma": f.pitch_sigma,
            "borderline": bool(f.borderline), "supported_pct": f.supported_pct, "points": int(f.points),
            "rms_ft": round(f.rms_m * FT, 3), "plane_eq": plane_eq_ft(f, ground_z_m)})
        blocks.append({"id": f"b{k}", "form": "flat" if flat_kind else "shed", "polygon": pts, "pitch_rise": pitch,
                       "ridge_azimuth_deg": None, "gable_edges": [], "plan_area_sqft": area,
                       "eave_height_ft": _eave_height_ft(f, ring, ground_z_m),
                       **({} if flat_kind else {"aspect_deg": float(f.aspect_deg)})})
    return facets, blocks, kept


def _edge_dicts(res: EngineResult, kept: set[str]) -> list[dict]:
    out = []
    for n, e in enumerate((e for e in res.edges if all(i in kept for i in e.facets)), start=1):
        d: dict[str, Any] = {"id": f"e{n}", "type": e.type,
                             "points": [[e.p0[0] * FT, e.p0[1] * FT], [e.p1[0] * FT, e.p1[1] * FT]],
                             "length_ft": float(e.length_ft), "facets": list(e.facets)}
        if e.type in ("level_change", "step_flashing", "wall_flashing") and e.jump_ft is not None:
            d["jump_ft"] = float(e.jump_ft)
        if e.high_edge:
            d["high_edge"] = True
        out.append(d)
    return out


def priced_area_check(res: EngineResult) -> dict[str, Any]:
    """The drawn area, and whether the priced area lies between the wall-line area and the drawn area."""
    drawn = float(sum(f.area_sqft for f in res.facets))
    priced = res.totals.get("planes_surface_area_sqft")
    wall = res.totals.get("area_sqft_wall_line")
    ok = (priced is not None and wall is not None
          and wall - AREA_TOL_SQFT <= priced <= drawn + AREA_TOL_SQFT)
    return {"drawn": round(drawn, 1), "priced": priced, "wall_line": wall, "between": bool(ok)}


def engine_totals(res: EngineResult) -> dict[str, Any]:
    """The envelope totals the engine owns: the four cost-sheet keys with the PRICED values, and the 0.4 additions.

    The envelope's ``area_sqft``, ``squares``, ``planes_surface_area_sqft`` and ``roofing_pitched_sqft`` +
    ``roofing_flat_sqft`` are ONE number, the priced area (same rounding: the pitched and flat parts are rounded first
    and the area is their sum). ``area_sqft_roof_edge`` is the drawn (measured roof edge) area, ``area_sqft_wall_line``
    the wall-line one; the priced area is held between them (scaled, pitched and flat together, if it ever leaves).
    The inner ``model.totals`` describe the DRAWN facets. Keys whose value is None are left out.
    """
    t = {k: res.totals[k] for k in COST_KEYS if res.totals.get(k) is not None}
    chk = priced_area_check(res)
    t["area_sqft_roof_edge"] = chk["drawn"]
    if "roofing_pitched_sqft" in t and "roofing_flat_sqft" in t:
        pitched, flat = t["roofing_pitched_sqft"], t["roofing_flat_sqft"]
        priced = pitched + flat
        wall = chk["wall_line"]
        if wall is not None and priced > 0:
            target = min(max(priced, wall), chk["drawn"])
            if abs(target - priced) > 1e-9:
                pitched, flat = pitched * target / priced, flat * target / priced
        pitched, flat = round(pitched, 1), round(flat, 1)
        priced = round(pitched + flat, 1)
        t.update(roofing_pitched_sqft=pitched, roofing_flat_sqft=flat, roofing_pitched_squares=round(pitched / 100, 2),
                 roofing_flat_squares=round(flat / 100, 2), planes_surface_area_sqft=priced)
    if "planes_surface_area_sqft" in t:
        t["area_sqft"] = t["planes_surface_area_sqft"]
        t["squares"] = round(t["area_sqft"] / 100.0, 3)
    t["plane_count"] = len(res.facets)
    return t


def engine_model(res: EngineResult, base: Any, ground_z_m: float, source: dict[str, Any] | None = None,
                 params: EngineParams = DEFAULT, notes: list[str] | None = None) -> dict[str, Any]:
    """The validated roof model of an engine result. ``base`` is a ``classify.BlockSet`` carrying only the address,
    origin, footprint meta and lidar meta (no blocks). Raises ``ModelError`` when the result cannot be a model
    (refused, no facets, or a rule of the contract is broken)."""
    if res.refused:
        raise ModelError(f"the engine refused this roof: {res.quality.verdict}")
    facets, blocks, kept = _facet_dicts(res, ground_z_m)
    if not facets:
        raise ModelError("the engine produced no usable facet")
    edges = _edge_dicts(res, kept)
    meta = base.footprint_meta or {}
    lidar = base.lidar or {}
    src = dict(source or {})
    model: dict[str, Any] = {
        "schema": SCHEMA, "generated_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "address": dict(base.address), "origin": origin_of(base), "north_deg": 0, "units": "ft",
        "source": {"method": src.get("method", SOURCE_METHOD),
                   "footprint": {"provider": meta.get("provider"),
                                 "id": str(meta["id"]) if meta.get("id") is not None else None,
                                 "area_sqft": meta.get("area_sqft")},
                   "lidar": ({k: lidar.get(k) for k in ("project", "acquired", "points_on_roof", "density_per_m2")}
                             if lidar else None),
                   "solar": None, "from_planes": True, "engine": "planes/1", "engine_params": res.params_hash},
        "blocks": blocks, "facets": facets, "edges": edges, "holes": [],
        "totals": {**_totals(facets, edges),
                   "note": "These totals describe the DRAWN roof (the facets of this model, at the measured roof edge). "
                           "The envelope's totals are the priced ones."},
        "confidence": {"overall": "low" if res.quality.verdict != "ok" else "medium", "notes": [
            "Drawn from the measured roof planes by the plane engine: one facet per plane, edges typed from geometry.",
            *(notes or [])]},
        "warnings": [], "debug": {}}
    diag = edge_diagnostics(res.facets, params)  # heights from the planes: no points here
    model["debug"]["coplanar_seams"] = diag["mergeable"]  # kept key: facets with no line between them
    diag["seam_points_only"] = sum(1 for e in res.edges if e.type == "flat_seam")  # points show a step, the planes agree
    model["debug"]["edge_diagnostics"] = diag
    model["debug"]["area_check"] = priced_area_check(res)
    if res.diagnostics.get("priced_clip_error"):
        model["debug"]["priced_clip_error"] = res.diagnostics["priced_clip_error"]
    validate(model)
    return model


def engine_planes(model: dict[str, Any]) -> list[dict[str, Any]]:
    """``model.planes`` for an engine model: one entry per facet, in the shape of ``planes.Plane.to_dict``."""
    out = []
    for f in model["facets"]:
        eq = f["plane_eq"]
        pts = np.array(f["polygon"], float)
        h = float(np.mean(eq[0] * pts[:, 0] + eq[1] * pts[:, 1] + eq[2])) if len(pts) else 0.0
        out.append({"id": f["id"], "polygon": [list(p) for p in f["polygon"]], "pitch_rise": round(math.hypot(eq[0], eq[1]) * 12, 2),
                    "aspect_deg": f["aspect_deg"], "plan_area_sqft": f["plan_area_sqft"], "surface_area_sqft": f["area_sqft"],
                    "height_ft": round(h, 2), "rms_ft": f["rms_ft"], "filled_pct": 0.0, "plane_eq": list(eq),
                    "straighten_method": "engine"})
    return out
