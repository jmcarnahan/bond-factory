"""The agent's own score: how well a draft of blocks matches the measured LiDAR planes, before it finalizes.

``score_draft`` takes the draft exactly as ``finalize`` takes it, runs the same checks and the same harness steps the
pipeline will run (``complete_tiling``, the build check, ``build_model``) and measures the result with the quality
functions (``quality.plane_metrics``). It returns numbers the agent may cite and the planes it still gets wrong, so
the agent can iterate while the mismatch falls (the stopping rule in the prompt).
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from .agent_repair import advice, unbuildable
from .classify import BlockSet, Pt, RoofBlock, complete_tiling, polygons_of, ring_of
from .model import build_model
from .planes import Plane
from .quality import _matches, plane_metrics

WORST_PLANES = 6  # how many mismatched planes are listed (largest first)
REMAP_DIST_FT = 1.5  # a tiled edge this close to an old gable end (and parallel) is that gable end
REMAP_ANGLE_DEG = 15.0
SMALL_GAP_SQFT = 150.0  # the harness's own limit: a bigger unclaimed piece becomes a flat block


def _facet_at(plane: Plane, facets: list[tuple[Any, dict[str, Any]]]) -> dict[str, Any] | None:
    poly = plane.shape().buffer(0)
    best, best_area = None, 0.0
    for fp, f in facets:
        a = poly.intersection(fp).area
        if a > best_area:
            best, best_area = f, a
    return best


def mismatched_planes(planes: list[Plane], model: dict[str, Any]) -> list[dict[str, Any]]:
    """Planes whose best-overlap model facet differs in direction or pitch, largest first (what to fix next)."""
    from shapely.geometry import Polygon

    facets = []
    for f in model.get("facets", []):
        p = Polygon(f["polygon"]).buffer(0)
        if not p.is_empty:
            facets.append((p, f))
    out = []
    for pl in planes:
        f = _facet_at(pl, facets)
        if f is not None and _matches(pl, f):
            continue
        out.append({"plane": pl.id, "plan_area_sqft": round(pl.plan_area_sqft, 1), "pitch_rise": round(pl.pitch_rise, 2),
                    "aspect_deg": None if pl.aspect_deg is None else round(pl.aspect_deg, 1),
                    "height_ft": round(pl.height_ft, 1),
                    "model_has": None if f is None else {"block": f["block"], "pitch_rise": round(f["pitch_rise"], 2),
                                                          "aspect_deg": None if f.get("aspect_deg") is None
                                                          else round(f["aspect_deg"], 1)}})
    out.sort(key=lambda r: -r["plan_area_sqft"])
    return out[:WORST_PLANES]


def capture_gables(blocks: list[RoofBlock]) -> dict[int, list[tuple[Pt, Pt]]]:
    """The segments of each gable block's gable edges as the agent drew them (``complete_tiling`` re-rings blocks)."""
    out: dict[int, list[tuple[Pt, Pt]]] = {}
    for rb in blocks:
        if rb.form == "gable" and rb.gable_edges:
            n = len(rb.polygon)
            out[id(rb)] = [(rb.polygon[g], rb.polygon[(g + 1) % n]) for g in rb.gable_edges if 0 <= g < n]
    return out


def remap_gables(done: list[RoofBlock], captured: dict[int, list[tuple[Pt, Pt]]]) -> None:
    """Point ``gable_edges`` of tiled blocks at the edges that lie on the gable ends the agent chose.

    Tiling clips and re-rings a polygon, so its old edge indices name other edges. A new edge belongs to an old gable
    end when it is within ``REMAP_DIST_FT`` of that segment's line and within ``REMAP_ANGLE_DEG`` of its direction.
    A block that keeps no gable end becomes a hip (and says so).
    """
    for rb in done:
        old = captured.get(id(rb))
        if not old:
            continue
        n = len(rb.polygon)
        keep = []
        for i in range(n):
            a, b = rb.polygon[i], rb.polygon[(i + 1) % n]
            length = math.dist(a, b)
            if length < 0.3:
                continue
            for p, q in old:
                ang = abs(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]) - math.atan2(q[1] - p[1], q[0] - p[0])))
                ang = min(ang % 180.0, 180.0 - ang % 180.0)
                mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                if ang <= REMAP_ANGLE_DEG and LineString([p, q]).distance(mid) <= REMAP_DIST_FT:
                    keep.append(i)
                    break
        rb.gable_edges = keep
        if not keep:
            rb.form = "hip"
            rb.notes.append("The gable ends were lost when the block was fitted to the footprint; drawn as a hip.")


def build_draft(blocks: list[RoofBlock], blockset: BlockSet, source: dict[str, Any]
                ) -> tuple[dict[str, Any] | None, list[RoofBlock], str | None]:
    """``(model, tiled blocks, problem)``: the draft built the way the pipeline builds it, or why it cannot be."""
    captured = capture_gables(blocks)
    done, _pct, _notes = complete_tiling(blocks, blockset)
    remap_gables(done, captured)
    from .agent_partition import tidy_tiling  # (imports this module)

    tidy_tiling(done, blockset)
    bad = unbuildable(done)
    if bad:
        return None, done, advice([(rb, why, "?") for rb, why in bad], prefix="")
    try:
        return build_model(blockset, done, source, None), done, None
    except ValueError as exc:  # ModelError or a skeleton refusal: the agent reads it and changes the draft
        return None, done, " ".join(str(exc).split())[:200]


def score_draft(blocks: list[RoofBlock], blockset: BlockSet, planes: list[Plane], source: dict[str, Any]
                ) -> dict[str, Any]:
    """The report ``check_draft`` returns; ``valid`` False carries ``problem`` instead of numbers."""
    model, done, problem = build_draft(blocks, blockset, source)
    if model is None:
        return {"valid": False, "problem": problem}
    q = plane_metrics(planes, model)
    plane_area = sum(p.surface_area_sqft for p in planes)
    return {"valid": True, "plane_mismatch_pct": q["plane_mismatch_pct"], "model_uncovered_pct": q["model_uncovered_pct"],
            "model_area_sqft": round(model["totals"]["total_area_sqft"], 1), "planes_area_sqft": round(plane_area, 1),
            "blocks": [{"block": rb.id, "form": rb.form, "pitch_rise": rb.pitch_rise,
                        "plan_area_sqft": round(rb.poly.area, 1)} for rb in done],
            "worst_planes": mismatched_planes(planes, model),
            "target": "plane_mismatch_pct under 15, model_uncovered_pct under 10, model_area within 5 percent of "
                      "planes_area"}


def absorb_small_gaps(blocks: list[RoofBlock], footprint: Polygon, limit: float = SMALL_GAP_SQFT) -> int:
    """Give each small unclaimed piece of the footprint to the sloped block it shares the most boundary with.

    The harness would give such a piece to the nearest block by Voronoi cells on the outlines, which can hand a thin
    strip along the far side of the footprint to the wrong block and draw a self-touching outline. A piece the agent
    left next to its blocks (a cleaned rectangle that stops a foot short of the outline) belongs to its neighbour.
    Pieces of ``limit`` sqft or more are left alone (they become flat blocks); pieces touching no sloped block too.
    Returns how many pieces were absorbed.
    """
    sloped = [b for b in blocks if b.form != "flat"]
    if not sloped:
        return 0
    gap = footprint.difference(unary_union([b.poly for b in blocks]))
    moved = 0
    for piece in polygons_of(gap):
        if piece.area >= limit or piece.area < 0.05:
            continue
        shared = [(piece.buffer(0.05).intersection(b.poly.boundary).length, b) for b in sloped]
        length, owner = max(shared, key=lambda t: t[0])
        if length < 0.5:
            continue
        merged = unary_union([owner.poly, piece]).buffer(0)
        if merged.geom_type != "Polygon":
            continue
        owner.polygon = ring_of(merged.simplify(0.05), 0.0)
        moved += 1
    return moved
