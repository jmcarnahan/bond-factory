"""The global labelling and its clean-up: label raster, absorb clutter, vectorise, clean, merge, straighten.

Runs the pipeline for a schedule of smoothness weights (beta) and keeps the first result with a plausible facet
count (or the cheapest one). Metres, building frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from .absorb import absorb_labels
from .cleanup import clean_facets, close_gaps, merge_coplanar_facets, merge_small_facets, repair_items
from .errors import Ctx, EngineFailure
from .junk import absorb_edge_strips, absorb_enclosed_flat, absorb_flat_junk, merge_flat_fitting
from .raster import label_raster
from .straighten import straighten_partition
from .vectorise import vectorise


@dataclass
class PartitionRun:
    """One labelling attempt."""

    items: list  # [[label, Polygon]]
    planes: list  # planes after label merges
    qlab: np.ndarray  # label per inlier point after label merges
    labels: np.ndarray  # label raster
    origin: tuple[float, float, float]  # (minx, miny, cell)
    beta: float
    diag: dict[str, Any] = field(default_factory=dict)


def explode(items: list) -> list:
    """Split multi-part polygons into one item per part (parts under 0.02 m2 are dropped)."""
    return [[label, part] for label, poly in items
            for part in (list(poly.geoms) if hasattr(poly, "geoms") else [poly])
            if part.geom_type == "Polygon" and part.area > 0.02]


def _attempt(outline: Polygon, q: np.ndarray, qlab: np.ndarray, planes: list, theta: float, h: float,
             beta: float, ctx: Ctx) -> PartitionRun:
    p = ctx.p
    qlab2 = qlab.copy()
    pl2 = [pl.copy() for pl in planes]
    diag: dict[str, Any] = {}
    lab, origin = label_raster(outline, q, qlab2, pl2, h, beta, ctx)
    lab = absorb_labels(lab, origin, pl2, q, qlab2, diag, ctx)
    out = clean_facets(vectorise(lab, origin, pl2, ctx), outline, ctx)
    out, n_small = merge_small_facets(out, pl2, q, ctx)
    out, n_cop = merge_coplanar_facets(out, pl2, ctx)
    out, n_flat = merge_flat_fitting(out, pl2, q, ctx) if p.flat_merge_fitting else (out, 0)
    diag["flat_merged"] = n_flat
    out, n_junk = absorb_flat_junk(out, pl2, ctx) if p.junk_absorb else (out, 0)
    out, n_encl = absorb_enclosed_flat(out, pl2, outline, ctx) if p.enclosed_flat_absorb else (out, 0)
    diag["enclosed_flat_absorbed"] = n_encl
    diag["flat_junk_absorbed"] = n_junk
    diag["small_facets_merged"] = n_small
    diag["coplanar_facets_merged"] = n_cop
    out = straighten_partition(explode(out), outline, pl2, theta, ctx, q)
    out = clean_facets(out, outline, ctx)
    out, n_strip = absorb_edge_strips(out, pl2, outline, ctx) if p.strip_absorb else (out, 0)
    diag["edge_strips_absorbed"] = n_strip
    out, n_gap = close_gaps(out, outline, p)
    diag["gaps_closed"] = n_gap
    return PartitionRun(repair_items(out), pl2, qlab2, lab, origin, beta, diag)


def build_partition(outline: Polygon, q: np.ndarray, qlab: np.ndarray, planes: list, theta: float,
                    ctx: Ctx) -> tuple[PartitionRun, float]:
    """Label the outline's cells and produce the clean facet polygons. Returns (chosen run, grid step m)."""
    p = ctx.p
    h = max(p.grid_min_m, math.sqrt(outline.area / p.grid_cells_target))
    allowed = outline.area / p.beta_m2_per_facet + p.beta_extra_facets
    best: PartitionRun | None = None
    for beta in p.beta_schedule:
        ctx.check()
        run = _attempt(outline, q, qlab, planes, theta, h, beta, ctx)
        if best is None or len(run.items) < len(best.items) * p.beta_keep_ratio:
            best = run
        if len(run.items) <= allowed:
            best = run
            break
    if best is None:
        raise EngineFailure("empty beta_schedule")
    return best, h
