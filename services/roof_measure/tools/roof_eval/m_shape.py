"""Shape and cleanliness metrics, and the facet-vs-facet comparison used against truth geometry."""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .geom import FLAT_BAND, FLAT_RISE, PERIMETER_TYPES, RIDGE_HIP_TYPES, Roof, mk_poly

SMALL_FACET_SQFT = 30.0
SHORT_EDGE_FT = 3.0
AXIS_TOL_DEG = 7.0


def adiff(a: float, b: float) -> float:
    """Smallest angle between two directions taken modulo 180 degrees."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def dominant_axes(foot: Polygon) -> tuple[float, float] | None:
    """The building axes: the direction of the longest wall segment, and the longest one at least 15 degrees
    from it (else perpendicular). Degrees modulo 180. None for an empty outline."""
    if foot is None or foot.is_empty:
        return None
    g = foot if isinstance(foot, Polygon) else max(foot.geoms, key=lambda q: q.area)
    c = list(g.exterior.coords)
    segs = sorted(((math.dist(a, b), math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0)
                   for a, b in itertools.pairwise(c) if math.dist(a, b) > 0.3), reverse=True)
    if not segs:
        return None
    t1 = segs[0][1]
    t2 = next((t for _, t in segs if adiff(t, t1) > 15.0), (t1 + 90.0) % 180.0)
    return t1, t2


def axis_aligned_share(roof: Roof, foot: Polygon, tol: float = AXIS_TOL_DEG) -> float | None:
    """Share of edge length (plan) within ``tol`` degrees of either building axis (axes from the wall outline)."""
    ax = dominant_axes(foot)
    if ax is None:
        return None
    num = den = 0.0
    for e in roof.edges:
        ln = e.plan_m
        if ln < 0.05:
            continue
        t = math.degrees(math.atan2(e.p1[1] - e.p0[1], e.p1[0] - e.p0[0])) % 180.0
        den += ln
        if min(adiff(t, a) for a in ax) <= tol:
            num += ln
    return num / den if den > 0 else None


def offaxis_controllable_share(roof: Roof, foot: Polygon, tol: float = AXIS_TOL_DEG) -> float | None:
    """Share of edge length (plan) that is off the building axes (more than ``tol`` degrees from both) and is NOT a hip or
    valley running at 45 degrees (+- 10) to an axis: the off-axis length an engine can control."""
    ax = dominant_axes(foot)
    if ax is None:
        return None
    off = den = 0.0
    for e in roof.edges:
        ln = e.plan_m
        if ln < 0.05:
            continue
        den += ln
        t = math.degrees(math.atan2(e.p1[1] - e.p0[1], e.p1[0] - e.p0[0])) % 180.0
        if min(adiff(t, a) for a in ax) <= tol:
            continue
        if e.type in ("hip", "valley") and any(abs(adiff(t, a) - 45.0) <= 10.0 for a in ax):
            continue
        off += ln
    return off / den if den > 0 else None


def cleanliness(roof: Roof, foot: Polygon) -> dict[str, Any]:
    """Facet count, facets under 30 sqft (surface), edges under 3 ft (3D), axis-aligned share of edge length."""
    return {"facets": len(roof.facets),
            "facets_lt_30sqft": sum(1 for f in roof.facets if f.area_sqft < SMALL_FACET_SQFT),
            "edges": len(roof.edges),
            "edges_lt_3ft": sum(1 for e in roof.edges if e.length_ft < SHORT_EDGE_FT),
            "edges_lt_3ft_share": (sum(1 for e in roof.edges if e.length_ft < SHORT_EDGE_FT) / len(roof.edges)) if roof.edges else None,
            "offaxis_controllable_share": offaxis_controllable_share(roof, foot),
            "axis_share_7deg": axis_aligned_share(roof, foot)}


def flat_pitched(roof: Roof) -> dict[str, float]:
    """Surface areas (sqft) by the fitted plane: flat below 2.0/12, pitched at or above; plus squares and pitch."""
    flat, pitched = roof.area_where(True), roof.area_where(False)
    return {"area_sqft": flat + pitched, "squares": (flat + pitched) / 100.0, "flat_sqft": flat,
            "pitched_sqft": pitched, "flat_squares": flat / 100.0, "pitched_squares": pitched / 100.0,
            "pitch_weighted": roof.pitch_weighted()}


def lengths(roof: Roof) -> dict[str, float]:
    """Feet by edge type, plus perimeter = eave + rake + flat_edge, ridge_hip = ridge + hip."""
    by = roof.length_by_type()
    out = {k: by.get(k, 0.0) for k in ("eave", "rake", "ridge", "hip", "valley", "flat_edge", "level_change",
                                       "step_flashing", "wall_flashing", "transition")}
    out["perimeter"] = sum(by.get(k, 0.0) for k in PERIMETER_TYPES)
    out["ridge_hip"] = sum(by.get(k, 0.0) for k in RIDGE_HIP_TYPES)
    return out


def truth_polys(truth_facets: list[dict[str, Any]]) -> list[tuple[Polygon, float | None, str | None]]:
    """(polygon, pitch rise, declared roof_type) of the truth facets that have a usable polygon."""
    out = []
    for f in truth_facets or []:
        p = mk_poly(f.get("polygon"))
        if not p.is_empty:
            out.append((p, f.get("pitch_rise"), f.get("roof_type")))
    return out


def facet_iou(roof: Roof, truth_facets: list[dict[str, Any]]) -> dict[str, Any]:
    """Two-sided facet agreement. Hungarian assignment on pairwise plan IoU; the score is the sum of matched IoUs
    over max(result facets, truth facets), so an unmatched facet on either side scores 0. Also the IoU of the unions."""
    tp = truth_polys(truth_facets)
    rp = [f.poly for f in roof.facets]
    if not tp or not rp:
        return {"mean_iou": 0.0 if (tp or rp) else None, "union_iou": 0.0 if (tp or rp) else None,
                "matched": 0, "n_result": len(rp), "n_truth": len(tp)}
    m = np.zeros((len(rp), len(tp)))
    for i, a in enumerate(rp):
        for j, (b, _, _) in enumerate(tp):
            if a.intersects(b):
                u = a.union(b).area
                m[i, j] = a.intersection(b).area / u if u > 0 else 0.0
    ri, ci = linear_sum_assignment(-m)
    ua, ub = unary_union(rp), unary_union([p for p, _, _ in tp])
    un = ua.union(ub).area
    return {"mean_iou": float(m[ri, ci].sum() / max(len(rp), len(tp))),
            "union_iou": float(ua.intersection(ub).area / un) if un > 0 else None,
            "matched": int((m[ri, ci] > 0.1).sum()), "n_result": len(rp), "n_truth": len(tp)}


LABEL_AGREE_MIN = 0.60  # plan 3.7a: the label-to-label ceiling is about 0.68; below 0.60 the two labels disagree


def label_agreement(truths: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Two-run agreement of T2 labels: mean pairwise two-sided facet IoU between the label files that carry facets, and a
    ``disagree`` flag below 0.60. Disagreeing houses are KEPT (a human resolves them), only flagged. None with < 2 labels."""
    sets = [[p for p, _, _ in truth_polys(t["facets"])] for t in truths if t.get("tier") == "T2" and t.get("facets")]
    sets = [s for s in sets if s]
    if len(sets) < 2:
        return None
    ious = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            m = np.zeros((len(sets[i]), len(sets[j])))
            for a, p in enumerate(sets[i]):
                for b, q in enumerate(sets[j]):
                    if p.intersects(q):
                        u = p.union(q).area
                        m[a, b] = p.intersection(q).area / u if u > 0 else 0.0
            ri, ci = linear_sum_assignment(-m)
            ious.append(float(m[ri, ci].sum() / max(m.shape)))
    iou = sum(ious) / len(ious)
    return {"n_files": len(sets), "iou": iou, "disagree": iou < LABEL_AGREE_MIN}


def flat_pitched_agreement(roof: Roof, truth_facets: list[dict[str, Any]], band: float = FLAT_BAND) -> float | None:
    """Over the plan area where result and truth facets overlap, the share where both call the same type.
    Where either pitch is within +- ``band`` of 2.0/12 the call is indeterminate and counts as agreement.
    The truth type comes from its pitch_rise, else its declared roof_type."""
    tp = truth_polys(truth_facets)
    num = den = 0.0
    for f in roof.facets:
        for p, pitch, rtype in tp:
            if not f.poly.intersects(p):
                continue
            a = f.poly.intersection(p).area
            if a <= 0:
                continue
            den += a
            t_flat = (pitch < FLAT_RISE) if pitch is not None else (rtype == "flat")
            near = abs(f.pitch - FLAT_RISE) <= band or (pitch is not None and abs(pitch - FLAT_RISE) <= band)
            if near or t_flat == f.is_flat:
                num += a
    return num / den if den > 0 else None
