"""The priced roof edge: the drawn facets clipped to the outline built with the pricing overhang scale."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from .edges import build_edges
from .errors import Ctx, EngineTimeout
from .facets import SQM2SQFT
from .outline import build_outline
from .types import Edge, Facet


def priced_clip(facets: list[Facet], edges: list[Edge], outline: Polygon, q: np.ndarray, wall: Polygon,
                theta: float, county: bool, diag: dict[str, Any], ctx: Ctx, jump_pts: np.ndarray | None = None) -> tuple[list[Facet], list[Edge], Polygon]:
    """(facets, edges, outline) at the priced overhang scale; the drawn ones when the scales are equal or the
    clip fails (``diag['priced_clip_error']`` says so)."""
    p = ctx.p
    ps = p.overhang_scale
    eff = ps if county else min(ps, p.overhang_scale_roofedge)
    drawn = p.overhang_scale_draw if county else min(p.overhang_scale_draw, p.overhang_scale_roofedge)
    if abs(eff - drawn) <= 1e-9:  # the EFFECTIVE scales decide (a non-county outline caps both at the roof-edge scale)
        return facets, edges, outline
    try:
        os_ = build_outline(q, wall, theta, eff, p)[0]
        os_ = Polygon(os_.exterior) if os_.geom_type == "Polygon" else os_.convex_hull
        clip = os_.intersection(outline)
        if clip.geom_type != "Polygon":
            clip = max([g for g in getattr(clip, "geoms", []) if g.geom_type == "Polygon"], key=lambda g: g.area,
                       default=outline)
        out = []
        for f in facets:
            c = f.polygon.intersection(clip)
            parts = [g for g in (c.geoms if hasattr(c, "geoms") else [c]) if g.geom_type == "Polygon" and g.area > 0.02]
            if not parts:
                continue
            g_ = max(parts, key=lambda g: g.area)
            cosv = 1.0 / math.sqrt(1 + (f.pitch_rise / 12.0) ** 2)
            out.append(replace(f, polygon=g_, plan_area_sqft=g_.area * SQM2SQFT, area_sqft=g_.area * SQM2SQFT / cosv))
        return out, build_edges(out, q if jump_pts is None else jump_pts, ctx, reuse_verdicts=True), clip
    except EngineTimeout:
        raise
    except Exception as ex:  # noqa: BLE001 - the drawn result stands; the failure is reported, not raised
        diag["priced_clip_error"] = str(ex)[:80]
        diag["priced_fallback"] = True  # the priced totals are the drawn ones: quality_stage says so
        return facets, edges, outline
