"""Result types of the roof engine. Geometry is in metres in the world frame the caller gave (the engine's internal
building frame is rotated back before anything is returned); areas and lengths carry their unit in the name.

``RoofPoints`` is the library's roof point selection (``engine.points``); it is re-exported here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from shapely.geometry import Polygon

from .plane_math import aspect_deg, pitch_rise
from .points import RoofPoints

__all__ = ["Edge", "EngineResult", "Facet", "Outline", "Partition", "Plane", "Quality", "RoofPoints"]

M2FT = 1 / 0.3048


@dataclass(frozen=True)
class Plane:
    """One roof plane ``z = a*x + b*y + c`` (metres) with the points that support it."""

    a: float
    b: float
    c: float
    n_points: int = 0
    rms_m: float = 0.0

    @property
    def pitch_rise(self) -> float:
        """Rise per 12 of run."""
        return pitch_rise((self.a, self.b))

    @property
    def aspect_deg(self) -> float:
        """Downslope compass azimuth, 0 = north, 90 = east."""
        return aspect_deg((self.a, self.b))

    def to_dict(self) -> dict[str, Any]:
        return {"a": round(self.a, 5), "b": round(self.b, 5), "c": round(self.c, 4), "n_points": self.n_points,
                "rms_m": round(self.rms_m, 4), "pitch_rise": round(self.pitch_rise, 2),
                "aspect_deg": round(self.aspect_deg, 1) if math.hypot(self.a, self.b) > 1e-3 else 0.0}


@dataclass(frozen=True)
class Outline:
    """The roof edge: ``drawn`` is the one outline, the diagram's and the totals' (facets tile it)."""

    drawn: Polygon
    source: str  # the outline provider as given (e.g. "lariac")
    county: bool  # the given outline is a county wall line (so an overhang was measured and applied)
    overhang_measured_m: tuple[float | None, ...] = ()
    overhang_applied_m: tuple[float, ...] = ()
    support_area_m2: float = 0.0


@dataclass
class Partition:
    """The global labelling: a raster of plane labels (-1 outside the outline) on a regular grid."""

    labels: np.ndarray  # (ny, nx) int; row = y
    origin_x: float  # m: x of the lower-left corner of cell (0, 0), building frame
    origin_y: float
    cell_m: float
    planes: list[Plane] = field(default_factory=list)
    beta: float = 0.0  # smoothness weight of the chosen labelling

    def summary(self) -> dict[str, Any]:
        """Per label: cell count, area and bounding box in cells (the golden-file view of the raster)."""
        out: dict[str, Any] = {"grid": {"ny": int(self.labels.shape[0]), "nx": int(self.labels.shape[1]),
                                          "cell_m": round(self.cell_m, 4)}, "beta": self.beta, "labels": {}}
        for lab in sorted(int(v) for v in np.unique(self.labels)):
            ii, jj = np.nonzero(self.labels == lab)
            out["labels"][str(lab)] = {"cells": len(ii), "area_m2": round(len(ii) * self.cell_m ** 2, 2),
                                       "bbox_cells": [int(jj.min()), int(ii.min()), int(jj.max()), int(ii.max())]}
        return out


@dataclass
class Facet:
    """One roof facet: a polygon (metres) on one plane."""

    id: str
    polygon: Polygon
    plane: tuple[float, float, float]
    label: int  # index of the plane in the engine's plane list
    pitch_rise: float  # rise per 12 of the (regularised) plane
    aspect_deg: float  # downslope compass azimuth
    roof_type: str  # "flat" (< 2/12) or "pitched"
    plan_area_sqft: float
    area_sqft: float  # surface area (plan area / cos(slope))
    points: int
    rms_m: float
    pitch_fit: float | None = None  # independent pitch fit from the facet's own points
    pitch_sigma: float | None = None
    supported_pct: float | None = None
    borderline: bool = False  # pitch_fit +- 2 sigma straddles 2/12 and the facet is > 5% of the roof


@dataclass
class Edge:
    """A typed edge between two facets (or a facet and the outside); p0, p1 are (x, y, z) in metres."""

    type: str  # eave rake ridge hip valley flat_edge level_change step_flashing wall_flashing flat_seam transition
    p0: tuple[float, float, float]
    p1: tuple[float, float, float]
    length_ft: float
    facets: tuple[str, ...]
    jump_m: float | None = None
    jump_ft: float | None = None
    high_edge: bool = False  # exterior high edge of a pitched facet (typed ridge, never a wall type)
    upper: str | None = None  # a step (level_change, step_flashing, wall_flashing): the id of the HIGHER facet


@dataclass
class Quality:
    """Plan 3.9 signals and the verdict."""

    verdict: str = "ok"
    reasons: list[str] = field(default_factory=list)
    fit_all: float | None = None
    fit_covered: float | None = None
    coverage: float | None = None
    supported_pct: float | None = None
    density: float | None = None  # pts/m2 on the roof outline
    outline_shift: float | None = None
    parcel_match: str | None = None
    outline_source: str = ""
    roof_cover_of_outline: float | None = None
    extra_roof_ring_ratio: float | None = None
    tree_contact_pct: float | None = None
    fit_clear: float | None = None  # fit_all with canopy (returns well above the surface) left out: REPORTED only, poor_fit tests fit_all
    tree_cover_pct: float | None = None  # share of the roof returns that are canopy above the surface
    flat_share: float | None = None  # flat (under 2/12) area / total area, 0..1 (0.5.1)
    error: str | None = None
    brief: bool = False  # a refusal: only the density, the reason and the verdict are reported

    def to_dict(self) -> dict[str, Any]:
        """The reference's ``diagnostics.quality`` dict (same keys, same order)."""
        if self.error is not None:
            return {"verdict": self.verdict, "error": self.error}
        if self.brief:
            return {"engine": "planes/1", "density_pts_m2": self.density, "reasons": list(self.reasons),
                    "verdict": self.verdict}
        return {"engine": "planes/1", "fit_all": self.fit_all, "fit_covered": self.fit_covered,
                "coverage": self.coverage, "supported_pct": self.supported_pct, "density_pts_m2": self.density,
                "parcel_match": self.parcel_match, "outline_source": self.outline_source,
                "roof_cover_of_outline": self.roof_cover_of_outline,
                "extra_roof_ring_ratio": self.extra_roof_ring_ratio, "tree_contact_pct": self.tree_contact_pct,
                "fit_clear": self.fit_clear, "tree_cover_pct": self.tree_cover_pct,
                "outline_shift": self.outline_shift, "reasons": list(self.reasons), "verdict": self.verdict,
                "flat_share": self.flat_share}


@dataclass
class EngineResult:
    """What ``measure_roof`` returns. A refused result has no facets and ``quality.verdict`` says why."""

    facets: list[Facet]
    edges: list[Edge]
    outline: Outline | None
    totals: dict[str, Any]
    quality: Quality
    planes: list[Plane] = field(default_factory=list)
    partition: Partition | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)  # deterministic: no wall time in here
    timings: dict[str, float] = field(default_factory=dict)  # stage wall times; never part of a hashed output
    params_hash: str = ""

    @property
    def refused(self) -> bool:
        return not self.facets

    def to_result_json(self, slug: str = "") -> dict[str, Any]:
        """The harness result format (the spike's ``result.json`` minus wall time), so results can be diffed."""
        from .result_json import build_result_json

        return build_result_json(self, slug)
