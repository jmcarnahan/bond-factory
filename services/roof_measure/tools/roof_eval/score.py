"""Score one result against one house: truth-free metrics plus a comparison with every truth file present.

Edges are not taken on trust: ``roof.edges`` is replaced by the set recomputed from the facets (``edges_re``) before any
length, perimeter, level-change or cleanliness metric; the engine's own list is kept as ``roof.engine_edges`` for the
disagreement, false and unmarked level-change metrics. Engine-only wall types (step, wall flashing, parapet) are carried over.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from shapely.geometry import Polygon

from . import edges_re, m_fit, m_shape, m_truth, priced
from .geom import FLAT_RISE, Roof, load_roof

KEEP_ENGINE_TYPES = ("step_flashing", "wall_flashing", "parapet")


def verdict_ok(roof: Roof) -> bool:
    """A result counts as automatic when it has facets and its verdict is ``ok``. An engine that states no verdict
    (research candidates, the stored library result) is taken as ok when it has facets."""
    return bool(roof.facets) and roof.verdict in (None, "ok")


def metrics(roof: Roof, ref: np.ndarray, foot: Polygon, facet_ref: float | None = None) -> dict[str, Any]:
    """Every truth-free metric of a result as a flat dict (see the m_* and edges_re modules for each definition)."""
    fl = m_fit.false_level_change(roof, ref)
    rc = edges_re.recompute(roof, ref)
    es = edges_re.summary(rc, roof)
    roof.edges = rc.edges + [e for e in roof.engine_edges if e.type in KEEP_ENGINE_TYPES]
    fp, ln, cl = m_shape.flat_pitched(roof), m_shape.lengths(roof), m_shape.cleanliness(roof, foot)
    declared = roof.declared.get("area_sqft")
    pr = priced.priced(roof)
    pc = priced.consistency(roof, pr)
    wrong = sum(1 for f in roof.facets if f.declared_type in ("flat", "pitched") and (f.declared_type == "flat") != f.is_flat)
    union_sqft = roof.union.area * 10.763910416709722
    ov, gap = m_fit.overlap_sqft(roof), m_fit.tiling_gap_sqft(roof)
    return {"fit_all": m_fit.fit_all(roof, ref), "fit_covered": m_fit.fit_covered(roof, ref),
            "coverage": m_fit.coverage(roof, ref), "overlap_sqft": ov, "tiling_gap_sqft": gap,
            "overlap_share": ov / union_sqft if union_sqft else None, "tiling_gap_share": gap / union_sqft if union_sqft else None,
            "outline_gap_sqft": m_fit.outline_gap_sqft(roof), "n_ref": len(ref), **cl,
            "facet_count_ratio": len(roof.facets) / facet_ref if facet_ref else None,
            "facets_per_1000sqft": len(roof.facets) / (fp["area_sqft"] / 1000.0) if fp["area_sqft"] else None,
            "unsupported_facet_area_share": m_fit.unsupported_share(roof, ref),
            "outside_outline_area_share": m_fit.outside_outline_share(roof, foot),
            "false_level_change_share": fl["share"], "false_level_change_count": fl["count"],
            "level_change_unverified": fl["unverified"], "level_change_edges": fl["edges"],
            "false_unmarked_ft": fl["false_ft"] + es["unmarked_level_change_ft"], **es,
            **fp, "perimeter_ft": ln["perimeter"], "ridge_hip_ft": ln["ridge_hip"], "valley_ft": ln["valley"],
            "level_change_ft": ln["level_change"], "lengths": ln,
            "priced": pr, "priced_consistent": pc["ok"], "priced_inconsistent": int(pc["ok"] is False), "priced_why": pc["why"],
            "declared_area_err_pct": m_truth.pct(declared, fp["area_sqft"]) if declared else None,
            "roof_type_label_wrong": wrong, "invalid_facets": roof.invalid_facets, "flat_cut": FLAT_RISE}


def score_house(res: dict[str, Any] | None, ref: np.ndarray, foot: Polygon, truths: list[dict[str, Any]],
                rules: dict[str, Any] | None = None, facet_ref: float | None = None) -> dict[str, Any]:
    """The per-house record of the scorer. ``res`` None (no result written) gives ``status: no_result``."""
    if res is None:
        return {"status": "no_result", "automation": False, "automation_ok": False, "verdict": None}
    roof = load_roof(res)
    rec: dict[str, Any] = {"status": "ok" if roof.facets else "empty", "automation": bool(roof.facets),
                           "automation_ok": verdict_ok(roof), "verdict": roof.verdict}
    if not roof.facets:
        return rec
    rec["m"] = metrics(roof, ref, foot, facet_ref)
    files = [m_truth.compare(roof, t, rules) for t in truths]
    rec["truth_files"] = files
    by_tier: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        by_tier.setdefault(str(f.get("tier")), []).append(f)
    rec["truth"] = {k: m_truth.merge_tier(v) for k, v in sorted(by_tier.items())}
    rec["t2_labels"] = m_shape.label_agreement(truths)
    return rec
