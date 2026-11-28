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
from types import SimpleNamespace
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from ..model import EDGE_TYPES, SCHEMA, ModelError, origin_of, validate
from .edges import edge_diagnostics
from .params import DEFAULT, EngineParams
from .totals import roof_totals
from .types import EngineResult, Facet

FT = 1 / 0.3048
FLAT_KIND_RISE = 0.5  # contract 0.2: ``kind`` is flat under 0.5/12 (``roof_type`` cuts at 2.0/12)
MIN_ANGLE_DEG = 10.0  # model.validate rejects a facet corner sharper than this
SOURCE_METHOD = "lidar_skeleton"  # a validated METHODS value; a deliberate rename is a phase 3 job
# the totals the envelope carries beside the model's own (area, squares, the lengths by type): read from model.totals
COST_KEYS = ("planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "ridge_cap_ridge_hip_ft",
             "roofing_pitched_sqft", "roofing_flat_sqft", "roofing_pitched_squares", "roofing_flat_squares",
             "low_slope_confirm_sqft", "area_sqft_wall_line", "outline_perimeter_wall_ft", "overhang_ft_median",
             "flat_edge_ft", "level_change_ft", "complexity", "area_sqft_roof_edge")
FOOTPRINT_KEYS = ("area_sqft_wall_line", "squares_wall_line", "outline_perimeter_wall_ft", "overhang_ft_median",
                  "roof_edge_perimeter_geom_ft")  # engine totals that need the wall line or the outline polygon
AREA_TOL_SQFT = 0.5  # a facet whose polygon is smaller than this is dropped from the model


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
        if e.type == "level_change" and e.jump_ft is not None:
            d["jump_ft"] = float(e.jump_ft)
        if e.high_edge:
            d["high_edge"] = True
        out.append(d)
    return out


def _model_totals(res: EngineResult, facets: list[dict], edges: list[dict], params: EngineParams) -> dict[str, Any]:
    """``model.totals``: ``roof_totals`` over the facets and edges the model carries (so every total is the sum of
    them, as ``validate`` checks), in the model's shape plus the cost-sheet keys. The wall-line and outline numbers
    are the engine's. Keys whose value is None are left out."""
    rows = [SimpleNamespace(id=f["id"], area_sqft=f["area_sqft"], roof_type=f["roof_type"], pitch_rise=f["pitch_rise"])
            for f in facets]
    segs = [SimpleNamespace(type=e["type"], length_ft=e["length_ft"], facets=tuple(e["facets"]), high_edge=bool(e.get("high_edge")))
            for e in edges]
    t = roof_totals(rows, segs, {f["id"] for f in facets if f["borderline"]}, params)
    t.update({k: res.totals[k] for k in FOOTPRINT_KEYS if res.totals.get(k) is not None})
    t["total_area_sqft"] = t["area_sqft"]
    t["predominant_pitch_rise"] = t.pop("predominant_pitch")
    t["lengths_ft"] = {k: t["lengths_ft"].get(k, 0.0) for k in EDGE_TYPES}
    return {k: v for k, v in t.items() if v is not None}


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
        "totals": {**_model_totals(res, facets, edges, params),
                   "note": "Every total is the sum of the facets and edges of this model; the envelope's totals repeat them."},
        "confidence": {"overall": "low" if res.quality.verdict != "ok" else "medium", "notes": [
            "Drawn from the measured roof planes by the plane engine: one facet per plane, edges typed from geometry.",
            *(notes or [])]},
        "warnings": [], "debug": {}}
    diag = edge_diagnostics(res.facets, params)  # heights from the planes: no points here
    model["debug"]["coplanar_seams"] = diag["mergeable"]  # kept key: facets with no line between them
    diag["seam_points_only"] = sum(1 for e in res.edges if e.type == "flat_seam")  # points show a step, the planes agree
    model["debug"]["edge_diagnostics"] = diag
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
