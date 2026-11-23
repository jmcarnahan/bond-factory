"""Quality metrics: how far the model's facets are from what LiDAR saw. Numbers and reason codes, never a label.

The consumer decides what is good or rough. ``plane_metrics`` is pure; the pipeline calls it with the snapped planes
(``planes.py``) and the final model.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from shapely.geometry import Polygon
from shapely.ops import unary_union

from .classify import BlockSet, polygons_of
from .planes import Plane, snap_with_stats

ASPECT_TOL_DEG = 30.0
PITCH_TOL_RISE = 1.5  # rise over 12
SIMPLIFIED_EXTRA_PLANES = 3  # planes_lidar >= facets_model + this ...
SIMPLIFIED_MISMATCH_PCT = 30.0  # ... and the mismatch at least this
LOW_COVERAGE_PCT = 70.0
MISSES_AREA_PCT = 10.0  # model_uncovered_pct at or above this gives model_misses_roof_area
LEVEL_MIN_SHARE = 0.05  # a plane counts for level_spread_ft when it covers this share of the planes' area
FLAT_RISE = 0.5  # a plane or facet under this pitch (rise over 12) counts as flat
ENGINE_REASONS = ("low_density", "outline_mismatch", "poor_fit", "not_exact_parcel", "low_slope_confirm",
                  "priced_fallback", "planes_not_found")  # plane engine (contract 0.4); priced_fallback: priced totals are the drawn ones
REASONS = ("multi_plane_simplified", "low_outline_coverage", "sparse_lidar", "parcel_street_match",
           "other_buildings_on_parcel", "agent_failed_fell_back", "bad_lidar_block", "model_misses_roof_area", "quality_failed")
COPIED = ("parcel_street_match", "other_buildings_on_parcel", "agent_failed_fell_back")  # warning codes passed on


def _adiff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _facet_polys(model: dict[str, Any]) -> list[tuple[Polygon, dict[str, Any]]]:
    out = []
    for f in model.get("facets", []):
        try:
            p = Polygon(f["polygon"]).buffer(0)
        except (KeyError, ValueError, TypeError):
            continue
        if not p.is_empty:
            out.append((p, f))
    return out


def _is_flat(aspect: Any, pitch: Any, kind: str | None = None) -> bool:
    """Flat: no aspect, kind "flat", or a pitch under 0.5/12 (the model builder's flat bucket)."""
    return kind == "flat" or aspect is None or float(pitch or 0.0) < FLAT_RISE


def _matches(plane: Plane, facet: dict[str, Any]) -> bool:
    """Flat meets flat (a plane with no aspect or a pitch under 0.5/12 is flat, likewise a facet); sloped meets
    sloped within 30 degrees of aspect and 1.5/12 of pitch; flat never meets sloped."""
    plane_flat = _is_flat(plane.aspect_deg, plane.pitch_rise)
    facet_flat = _is_flat(facet.get("aspect_deg"), facet.get("pitch_rise"), facet.get("kind"))
    if plane_flat or facet_flat:
        return plane_flat and facet_flat
    return (_adiff(float(plane.aspect_deg), float(facet["aspect_deg"])) <= ASPECT_TOL_DEG  # type: ignore[arg-type]
            and abs(plane.pitch_rise - float(facet.get("pitch_rise") or 0.0)) <= PITCH_TOL_RISE)


def plane_mismatch_pct(planes: Sequence[Plane], model: dict[str, Any]) -> float | None:
    """Area-weighted share of planes whose best-overlap model facet differs in direction or pitch (None: no data)."""
    facets = _facet_polys(model)
    total = sum(p.plan_area_sqft for p in planes)
    if not planes or total <= 0:
        return None
    bad = 0.0
    for pl in planes:
        poly = pl.shape().buffer(0)
        best, best_area = None, 0.0
        for fp, f in facets:
            a = poly.intersection(fp).area
            if a > best_area:
                best, best_area = f, a
        if best is None or not _matches(pl, best):
            bad += pl.plan_area_sqft
    return 100.0 * bad / total


def extent_metrics(planes: Sequence[Plane], model: dict[str, Any]) -> tuple[float | None, float | None]:
    """``(model_uncovered_pct, level_spread_ft)``.

    ``model_uncovered_pct``: share of the snapped planes' total plan area that lies outside the union of the model's
    facets in plan view (0 for a model that covers every plane; 100 when the model has no facet). It sees the extent
    the model loses, which the mismatch (direction and pitch only) cannot. ``level_spread_ft``: highest minus lowest
    plane height above ground among the planes that cover at least 5% of the planes' area (a two-level roof shows a
    spread of several feet). Both None when there are no planes.
    """
    total = sum(p.plan_area_sqft for p in planes)
    if not planes or total <= 0:
        return None, None
    polys = [fp for fp, _ in _facet_polys(model)]
    outside = 0.0
    if polys:
        union = unary_union(polys)
        outside = sum(max(0.0, pl.shape().buffer(0).difference(union).area) for pl in planes)
    else:
        outside = total
    big = [p.height_ft for p in planes if p.plan_area_sqft >= LEVEL_MIN_SHARE * total]
    return 100.0 * min(outside, total) / total, (max(big) - min(big) if big else None)


def plane_metrics(planes: Sequence[Plane], model: dict[str, Any], *, covered_pct: float | None = None,
                  warning_codes: Iterable[str] = ()) -> dict[str, Any]:
    """The ``model.quality`` object: mismatch, coverage, counts and reason codes (values rounded to 0.1).

    ``covered_pct`` is the share of the outline the raw cleaned planes covered before gap filling (from
    ``planes.SnapResult.covered_pct``); when omitted it is derived from the planes' ``filled_pct``.
    ``warning_codes`` are the envelope's warning codes: ``low_point_density`` (as ``sparse_lidar``),
    ``parcel_street_match``, ``other_buildings_on_parcel`` and ``agent_failed_fell_back`` become reason codes.
    ``model_uncovered_pct`` and ``level_spread_ft`` are described in ``extent_metrics``.
    """
    codes = set(warning_codes)
    mismatch = plane_mismatch_pct(planes, model)
    if covered_pct is None and planes:
        total = sum(p.plan_area_sqft for p in planes)
        covered_pct = 100.0 * sum(p.plan_area_sqft * (1 - p.filled_pct / 100.0) for p in planes) / total if total else None
    n_planes, n_facets = len(planes), len(model.get("facets", []))
    reasons: list[str] = []
    if mismatch is not None and n_planes >= n_facets + SIMPLIFIED_EXTRA_PLANES and mismatch >= SIMPLIFIED_MISMATCH_PCT:
        reasons.append("multi_plane_simplified")
    if covered_pct is not None and covered_pct < LOW_COVERAGE_PCT:
        reasons.append("low_outline_coverage")
    uncovered, spread = extent_metrics(planes, model)
    if uncovered is not None and uncovered >= MISSES_AREA_PCT:
        reasons.append("model_misses_roof_area")
    if "low_point_density" in codes:
        reasons.append("sparse_lidar")
    for code in COPIED:  # warning codes that are passed on as they are
        if code in codes:
            reasons.append(code)
    return {"plane_mismatch_pct": None if mismatch is None else round(mismatch, 1),
            "outline_covered_pct": None if covered_pct is None else round(covered_pct, 1),
            "model_uncovered_pct": None if uncovered is None else round(uncovered, 1),
            "level_spread_ft": None if spread is None else round(spread, 1),
            "planes_lidar": n_planes, "facets_model": n_facets, "reasons": reasons}


def plane_totals(planes: Sequence[Plane]) -> dict[str, Any]:
    """The four envelope totals derived from the snapped planes (surface area, pitch, outline perimeter, count)."""
    plan = sum(p.plan_area_sqft for p in planes)
    outline = unary_union([p.shape().buffer(0) for p in planes])
    return {"planes_surface_area_sqft": round(sum(p.surface_area_sqft for p in planes), 1),
            "planes_pitch_weighted": round(sum(p.plan_area_sqft * p.pitch_rise for p in planes) / plan, 1) if plan else 0.0,
            "outline_perimeter_ft": round(sum(g.exterior.length for g in polygons_of(outline)), 1),
            "plane_count": len(planes)}


def failed_assessment(model: dict[str, Any], codes: Iterable[str] = (), planes_lidar: int = 0) -> dict[str, Any]:
    """What the envelope carries when the assessment could not be made: no numbers, reason ``quality_failed``.

    A consumer can then tell "the check failed" (this) from "no LiDAR blocks" (no ``quality`` key at all).
    """
    codes = set(codes)
    return {"quality": {"plane_mismatch_pct": None, "outline_covered_pct": None, "model_uncovered_pct": None,
                        "level_spread_ft": None, "planes_lidar": planes_lidar,
                        "facets_model": len(model.get("facets", [])),
                        "reasons": ["quality_failed", *[c for c in COPIED if c in codes]]}}


def assess(blockset: BlockSet, model: dict[str, Any], warning_codes: Iterable[str]) -> dict[str, Any] | None:
    """Snap the LiDAR planes and measure the model against them; None when the block set has no blocks.

    Returns ``{"quality", "planes", "totals"}``: the objects the envelope adds (``model.quality``,
    ``model.planes``) and the four extra totals. The planes are clipped to the footprint unless the parcel was only
    a street match (then the footprint may belong to the neighbour); coverage is measured on the footprint either
    way. When snapping fails (or the footprint has no area) the result is ``failed_assessment``; when it runs but no
    plane survives, quality still reports ``outline_covered_pct`` (0.0 when no plane touches the footprint) and
    ``low_outline_coverage``, ``planes`` is ``[]`` and the plane totals are absent.
    """
    codes = list(warning_codes)
    if not blockset.blocks:
        return None
    snap = snap_with_stats(blockset, clip_to_footprint="parcel_street_match" not in codes)
    if snap.failed or snap.footprint_area_sqft <= 0:  # (a footprint without area cannot be judged)
        return failed_assessment(model, codes, len(blockset.blocks))
    quality = plane_metrics(snap.planes, model, covered_pct=snap.covered_pct, warning_codes=codes)
    if snap.bad_blocks:  # NaN/infinite LiDAR blocks were left out: say so
        quality["reasons"].append("bad_lidar_block")
    if not snap.planes:
        return {"quality": quality, "planes": [], "totals": {}}
    return {"quality": quality, "planes": [p.to_dict() for p in snap.planes], "totals": plane_totals(snap.planes)}


# ----------------------------------------------------------------------------- the plane engine (contract 0.4)
ENGINE_COPIED = (*COPIED, "not_exact_parcel")


def engine_quality(res: Any, model: dict[str, Any], warning_codes: Iterable[str] = ()) -> dict[str, Any]:
    """``model.quality`` of an engine result: the contract-0.4 signals, and the older keys with their engine analogues.

    New keys: ``engine``, ``fit_covered``, ``fit_all``, ``coverage``, ``supported_pct``, ``density_pts_m2``,
    ``parcel_match``, ``outline_source``, ``overhang_scale``, ``verdict``, ``outline_shift`` and ``reasons``.
    Old keys, so a reader that knows only 0.3 still gets numbers: ``plane_mismatch_pct`` = share of roof points off
    their facet's plane (100 x (1 - fit_covered)), ``outline_covered_pct`` = roof-point support over the outline,
    ``model_uncovered_pct`` = share of roof points outside every facet, ``level_spread_ft``, ``planes_lidar`` (planes
    used) and ``facets_model``.
    """
    q = res.quality
    codes = set(warning_codes)
    facets = model.get("facets", [])
    big = [f for f in facets if f["plan_area_sqft"] >= LEVEL_MIN_SHARE * sum(g["plan_area_sqft"] for g in facets)]
    heights = [sum(f["plane_eq"][0] * x + f["plane_eq"][1] * y + f["plane_eq"][2] for x, y in f["polygon"]) / len(f["polygon"])
               for f in big]

    def pct(v: float | None) -> float | None:
        return None if v is None else round(100.0 * v, 1)

    reasons = [r for r in q.reasons if r != "lidar_too_sparse"]
    if res.totals.get("low_slope_confirm_sqft"):
        reasons.append("low_slope_confirm")
    reasons += [c for c in ENGINE_COPIED if c in codes and c not in reasons]
    return {
        "engine": "planes/1", "engine_params": res.params_hash, "verdict": q.verdict, "fit_covered": q.fit_covered, "fit_all": q.fit_all,
        "fit_clear": q.fit_clear, "tree_cover_pct": q.tree_cover_pct, "coverage": q.coverage, "supported_pct": q.supported_pct, "density_pts_m2": q.density,
        "parcel_match": q.parcel_match, "outline_source": q.outline_source, "overhang_scale": q.overhang_scale,
        "outline_shift": q.outline_shift, "flat_share": q.flat_share,
        "plane_mismatch_pct": None if q.fit_covered is None else round(100.0 * (1.0 - q.fit_covered), 1),
        "outline_covered_pct": None if q.roof_cover_of_outline is None else round(min(100.0, 100.0 * q.roof_cover_of_outline), 1),
        "model_uncovered_pct": None if q.coverage is None else round(100.0 * (1.0 - q.coverage), 1),
        "level_spread_ft": round(max(heights) - min(heights), 1) if heights else None,
        "planes_lidar": len({f.label for f in res.facets}),
        "facets_model": len(facets), "reasons": reasons}


def assess_engine(res: Any, model: dict[str, Any], warning_codes: Iterable[str] = ()) -> dict[str, Any]:
    """The assessment ``envelope.build_envelope`` takes for an engine result: ``{"quality", "planes", "totals"}``."""
    from .engine.adapter import engine_planes, engine_totals

    return {"quality": engine_quality(res, model, warning_codes), "planes": engine_planes(model),
            "totals": engine_totals(res)}
