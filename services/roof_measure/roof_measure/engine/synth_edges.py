"""Synthetic scenes for the roof-edge finder: things beside a roof edge that are not roof, with the exact roof known.

Each function takes a ``SynthRoof`` and the (N, 4) cloud ``simulate`` made of it and returns a new cloud with
something added next to one edge: a neighbour's wall and roof, a flat cover at eave height, a cover continuing the roof
plane, a tree crown over a corner (the roof and the ground under it mostly hidden). Returns are class 1 (like the
survey's unclassified roofs and trees), ground class 2; the ground a solid object hides is removed. ``jog_gable`` is a
roof whose eave steps out over part of its length while the wall line is straight. Local metric frame, metres; one
seeded generator per call (the same arguments give the same bytes).
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import Polygon, box

from .synth_points import EAVE_M, OVERHANG_M, _m
from .synth_shapes import SynthRoof, Wing, build


def _slab(rng, rect: tuple, density: float, z) -> np.ndarray:
    """Returns over the plan rectangle ``rect`` (x0, y0, x1, y1) at heights ``z(x, y)``, class 1."""
    x0, y0, x1, y1 = rect
    n = rng.poisson(density * (x1 - x0) * (y1 - y0))
    x, y = rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)
    return np.column_stack([x, y, z(x, y) + rng.normal(0.0, 0.03, n), np.ones(n)])


def _hide_ground(pts: np.ndarray, area: Polygon, keep: float, rng) -> np.ndarray:
    """Drop the ground returns under ``area`` (all but a share ``keep``)."""
    under = (pts[:, 3] == 2) & shapely.contains_xy(area, pts[:, 0], pts[:, 1])
    return pts[~(under & (rng.uniform(size=len(pts)) >= keep))]


def _edge_z(roof: SynthRoof, x: float, y: float) -> float:
    """Roof height at (x, y): the highest facet plane among the facets that hold the point (eave side: nearest one)."""
    f = min(roof.facets, key=lambda f: f.polygon().distance(shapely.Point(x, y)))
    return f.z(x, y)


def neighbour(roof: SynthRoof, pts: np.ndarray, *, gap_m: float = 1.2, density: float = 8.0, seed: int = 11) -> np.ndarray:
    """A neighbour's flat roof 0.5 m above our eave starting ``gap_m`` beyond the east roof edge (6 m deep, the edge's
    length), with returns on its west wall from the ground up."""
    rng = np.random.default_rng(seed)
    _x0, y0, x1, y1 = Polygon(roof.roof_outline).bounds
    top = EAVE_M + 0.5
    nb = (x1 + gap_m, y0, x1 + gap_m + 6.0, y1)
    deck = _slab(rng, nb, density, lambda x, y: np.full(len(x), top))
    k = rng.poisson(density * 0.3 * (y1 - y0) * top)  # oblique pulses see the wall face
    wall = np.column_stack([np.full(k, x1 + gap_m) + rng.uniform(0, 0.05, k), rng.uniform(y0, y1, k),
                            rng.uniform(0.2, top, k), np.ones(k)])
    return np.vstack([_hide_ground(pts, box(*nb), 0.0, rng), deck, wall])


def flat_cover(roof: SynthRoof, pts: np.ndarray, *, u: tuple[float, float] = (0.35, 0.65), depth_m: float = 3.0,
               dz_m: float = 0.0, density: float = 8.0, seed: int = 12) -> np.ndarray:
    """A flat cover touching the south eave at the eave's height (+ ``dz_m``), ``depth_m`` deep, over the share ``u``
    of the eave's length (``(0, 1)``: all of it). The ground under it is hidden."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, _y1 = Polygon(roof.roof_outline).bounds
    a, b = x0 + u[0] * (x1 - x0), x0 + u[1] * (x1 - x0)
    z = _edge_z(roof, (a + b) / 2, y0) + dz_m
    rect = (a, y0 - depth_m, b, y0)
    return np.vstack([_hide_ground(pts, box(*rect), 0.0, rng), _slab(rng, rect, density, lambda x, y: np.full(len(x), z))])


def plane_cover(roof: SynthRoof, pts: np.ndarray, *, u: tuple[float, float] = (0.35, 0.65), depth_m: float = 3.0,
                density: float = 8.0, seed: int = 13) -> np.ndarray:
    """A cover continuing the south roof plane at the same pitch, ``depth_m`` past the eave, over the share ``u``."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, _y1 = Polygon(roof.roof_outline).bounds
    a, b = x0 + u[0] * (x1 - x0), x0 + u[1] * (x1 - x0)
    f = min(roof.facets, key=lambda f: f.polygon().distance(shapely.Point((a + b) / 2, y0)))
    rect = (a, y0 - depth_m, b, y0)
    pl = f.plane
    return np.vstack([_hide_ground(pts, box(*rect), 0.0, rng),
                      _slab(rng, rect, density, lambda x, y: pl[0] * x + pl[1] * y + pl[2])])


def corner_tree(roof: SynthRoof, pts: np.ndarray, *, radius_m: float = 2.5, keep: float = 0.2, density: float = 8.0,
                seed: int = 14) -> np.ndarray:
    """A tree crown centred on the roof's south-east corner: 0.5-3 m above the roof, ``keep`` of the roof and ground
    returns under it survive."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = Polygon(roof.roof_outline).bounds
    c = np.array([x1, y0])
    under = np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1]) < radius_m
    pts = pts[~(under & (rng.uniform(size=len(pts)) >= keep))]
    m = rng.poisson(density * np.pi * radius_m ** 2 * 1.3)
    rho, ang = radius_m * np.sqrt(rng.uniform(size=m)), rng.uniform(0, 2 * np.pi, m)
    x, y = c[0] + rho * np.cos(ang), c[1] + rho * np.sin(ang)
    base = np.array([_edge_z(roof, xi, yi) for xi, yi in zip(np.clip(x, x0, x1), np.clip(y, y0, y1), strict=True)])
    z = base + 0.5 + 2.5 * np.sqrt(np.clip(1 - (rho / radius_m) ** 2, 0, 1)) * rng.uniform(0.2, 1.0, m)
    return np.vstack([pts, np.column_stack([x, y, z, np.ones(m)])])


def fascia(roof: SynthRoof, pts: np.ndarray, *, density: float = 8.0, seed: int = 15) -> np.ndarray:
    """Returns on the south fascia and wall face just past the eave (oblique pulses): 0-0.1 m outside the roof edge,
    from 0.1 m to 2 m below the eave line, as real roofs show where the roof ends at a wall drop."""
    rng = np.random.default_rng(seed)
    x0, y0, x1, _ = Polygon(roof.roof_outline).bounds
    n = rng.poisson(density * 0.5 * (x1 - x0))
    x = rng.uniform(x0, x1, n)
    z = np.array([_edge_z(roof, xi, y0) for xi in x]) - rng.uniform(0.1, 2.0, n)
    return np.vstack([pts, np.column_stack([x, y0 - rng.uniform(0.0, 0.1, n), z, np.ones(n)])])


def jog_gable(length_ft: float = 40.0, width_ft: float = 26.0, pitch: float = 6.0, jog_m: float = 0.6,
              at_ft: float = 22.0) -> SynthRoof:
    """A gable whose south eave overhangs ``jog_m`` more east of ``at_ft`` than west of it; the wall line is one
    rectangle, so the step is in the roof edge only."""
    o = OVERHANG_M
    w = [Wing((0.0, 0.0, _m(at_ft), _m(width_ft)), "SN", pitch, EAVE_M, (o, o, 0.0, o)),
         Wing((_m(at_ft), 0.0, _m(length_ft), _m(width_ft)), "SN", pitch, EAVE_M, (0.0, o + jog_m, o, o))]
    return build("jog_gable", w, {"jog_m": jog_m, "pitch": pitch})
