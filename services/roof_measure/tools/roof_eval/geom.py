"""Result loading and shared geometry: a CONTRACT-1 result.json becomes a ``Roof`` of shapely facets and 3D edges.

Units: local frame in METRES in, sqft and feet out. Nothing the engine declares about areas or lengths is trusted:
areas are recomputed from the polygons and planes, lengths from the edge end points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

M2_TO_SQFT = 10.763910416709722
M_TO_FT = 1.0 / 0.3048
FLAT_RISE = 2.0  # pitch (rise per 12) below which a facet is flat
FLAT_BAND = 0.5  # +- band around FLAT_RISE inside which flat/pitched is indeterminate
PERIMETER_TYPES = ("eave", "rake", "flat_edge")
RIDGE_HIP_TYPES = ("ridge", "hip")
EDGE_TYPES = ("eave", "rake", "ridge", "hip", "valley", "step_flashing", "wall_flashing", "parapet",
              "transition", "flat_edge", "level_change", "flat_seam", "unspecified")
# a step between two roofs, by name: the engine says sidewall / headwall / level change, the harness's recomputed edge list says level_change
STEP_TYPES = ("level_change", "step_flashing", "wall_flashing")
# drawn, never priced, never counted: a seam between two flat facets that is not a real level change (contract 0.4 / 0.5.1).
# Harness metrics that walk edges (lengths, the false level-change share, cleanliness edge counts) must ignore it.
UNCOUNTED_EDGE_TYPES = ("flat_seam",)


@dataclass
class Facet:
    id: str
    poly: Polygon
    plane: tuple[float, float, float]  # z = a x + b y + c (metres)
    declared_type: str | None = None
    declared_pitch: float | None = None

    @property
    def pitch(self) -> float:
        """Rise per 12 of the fitted plane."""
        return 12.0 * math.hypot(self.plane[0], self.plane[1])

    @property
    def is_flat(self) -> bool:
        return self.pitch < FLAT_RISE

    @property
    def plan_sqft(self) -> float:
        return self.poly.area * M2_TO_SQFT

    @property
    def area_sqft(self) -> float:
        """Surface area: plan area times sqrt(1 + slope^2), exact for a plane."""
        return self.plan_sqft * math.sqrt(1.0 + self.plane[0] ** 2 + self.plane[1] ** 2)

    def z_at(self, x, y):
        return self.plane[0] * x + self.plane[1] * y + self.plane[2]


@dataclass
class Edge:
    type: str
    p0: tuple[float, float, float]
    p1: tuple[float, float, float]
    facets: list[str] = field(default_factory=list)
    declared_ft: float | None = None
    high_edge: bool = False  # a pitched facet's level HIGH outline edge (typed rake, never ridge or eave)

    @property
    def plan_m(self) -> float:
        return math.hypot(self.p1[0] - self.p0[0], self.p1[1] - self.p0[1])

    @property
    def length_ft(self) -> float:
        """3D length in feet from the end points."""
        return math.dist(self.p0, self.p1) * M_TO_FT


@dataclass
class Roof:
    facets: list[Facet]
    edges: list[Edge]
    outline: Any  # shapely geometry (may be empty)
    verdict: str | None
    declared: dict[str, Any]
    invalid_facets: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
    engine_edges: list[Edge] = field(default_factory=list)  # the engine's own list; ``edges`` is replaced by the recomputed set

    @property
    def union(self):
        return unary_union([f.poly for f in self.facets if not f.poly.is_empty]) if self.facets else Polygon()

    @property
    def area_sqft(self) -> float:
        return sum(f.area_sqft for f in self.facets)

    @property
    def squares(self) -> float:
        return self.area_sqft / 100.0

    def area_where(self, flat: bool) -> float:
        return sum(f.area_sqft for f in self.facets if f.is_flat == flat)

    @property
    def counted_edges(self) -> list[Edge]:
        """The edges metrics may count: every edge except the drawn-only types (``flat_seam``)."""
        return [e for e in self.edges if e.type not in UNCOUNTED_EDGE_TYPES]

    def length_by_type(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self.counted_edges:
            out[e.type] = out.get(e.type, 0.0) + e.length_ft
        return out

    def pitch_weighted(self) -> float | None:
        """Area-weighted pitch (rise per 12) of the pitched facets; None when there are none."""
        pf = [f for f in self.facets if not f.is_flat]
        a = sum(f.area_sqft for f in pf)
        return sum(f.pitch * f.area_sqft for f in pf) / a if a > 0 else None


def mk_poly(ring) -> Polygon:
    """Polygon from a ring [[x, y], ...] or a list of rings (exterior first); repaired when invalid; empty on junk."""
    if not ring or len(ring) < 3:
        return Polygon()
    rings = [ring] if isinstance(ring[0][0], (int, float)) else list(ring)
    try:
        p = Polygon([(float(a[0]), float(a[1])) for a in rings[0]],
                    [[(float(a[0]), float(a[1])) for a in r] for r in rings[1:] if len(r) >= 3])
    except (TypeError, ValueError, IndexError):
        return Polygon()
    return p if p.is_valid else p.buffer(0)


def rings_of(outline) -> list:
    """roof_outline may be one ring [[x, y], ...] or a list of rings."""
    if not outline:
        return []
    return [outline] if isinstance(outline[0][0], (int, float)) else list(outline)


def _p3(p) -> tuple[float, float, float]:
    return float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0


def load_roof(res: dict[str, Any]) -> Roof:
    """Parse a CONTRACT-1 result (extended: level_change/flat_edge edges, diagnostics.quality.verdict)."""
    facets: list[Facet] = []
    bad = 0
    for i, f in enumerate(res.get("facets") or []):
        poly = mk_poly(f.get("polygon"))
        pl = f.get("plane")
        if poly.is_empty or not pl or len(pl) != 3:
            bad += 1
            if poly.is_empty:
                continue
            pl = (0.0, 0.0, 0.0)  # no plane: scored as flat at z = 0, so every point misses
        facets.append(Facet(str(f.get("id", f"f{i + 1}")), poly, (float(pl[0]), float(pl[1]), float(pl[2])),
                            f.get("roof_type"), f.get("pitch_rise")))
    edges: list[Edge] = []
    for e in res.get("edges") or []:
        try:
            t = e.get("type") if e.get("type") in EDGE_TYPES else "unspecified"
            edges.append(Edge(t, _p3(e["p0"]), _p3(e["p1"]), list(e.get("facets") or []), e.get("length_ft")))
        except (KeyError, TypeError, IndexError):
            bad += 1
    outline = unary_union([mk_poly(r) for r in rings_of(res.get("roof_outline"))] or [Polygon()])
    diag = res.get("diagnostics") or {}
    verdict = (diag.get("quality") or {}).get("verdict") if isinstance(diag.get("quality"), dict) else None
    return Roof(facets, edges, outline, verdict, dict(res.get("totals") or {}), bad, res, list(edges))


def surface_points(roof: Roof, xy: np.ndarray) -> np.ndarray:
    """First-containing facet index per point (-1 = in no facet). Boundary points count as contained."""
    import shapely

    idx = np.full(len(xy), -1, dtype=int)
    for i, f in enumerate(roof.facets):
        if f.poly.is_empty:
            continue
        minx, miny, maxx, maxy = f.poly.bounds
        cand = np.where((idx < 0) & (xy[:, 0] >= minx) & (xy[:, 0] <= maxx) & (xy[:, 1] >= miny) & (xy[:, 1] <= maxy))[0]
        if len(cand):
            hit = shapely.intersects_xy(f.poly, xy[cand, 0], xy[cand, 1])
            idx[cand[hit]] = i
    return idx
