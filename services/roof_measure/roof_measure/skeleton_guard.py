"""Validation of every ring that reaches CGAL's straight skeleton, and the safe gable extension.

WHY: ``compas_cgal`` has no input validation. A self-intersecting ring (a bow-tie, a repeated vertex, a ring that
touches itself) is undefined behaviour in CGAL: a segfault or an endless loop, which no ``except`` can catch.
``_extend_for_gables`` produces exactly such a ring when the two edges next to a gable end converge toward the side
the gable edge is pushed to. So the ring is checked with shapely before the one native call, and the extension
distance shrinks until the extended ring is valid (rectangles pass on the first try and are unchanged).
"""

from __future__ import annotations

import math
from collections.abc import Callable

from shapely.geometry import Polygon

Pt = tuple[float, float]

MIN_AREA_SQFT = 1e-6  # HEAD handled edges down to 1e-5 ft and tiny areas: the guard only refuses what CGAL cannot take
MIN_EDGE_FT = 5e-6


def _signed_area(p: list[Pt]) -> float:
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def check_ring(pts: list[Pt], what: str = "polygon") -> None:
    """Raise ValueError (the agent loop shows it to the model) unless ``pts`` is a safe CCW ring for CGAL.

    Safe means: at least 3 distinct vertices, no repeated consecutive vertex and no edge under ``MIN_EDGE_FT``, a
    simple ring (no crossing, no touching, shapely-valid), counter-clockwise, and an area above ``MIN_AREA_SQFT``.
    Collinear vertices are allowed (CGAL handles them).
    """
    n = len(pts)
    if len(set(pts)) < 3:
        raise ValueError(f"{what}: needs at least 3 distinct vertices")
    for i in range(n):
        if pts[i] == pts[(i + 1) % n]:
            raise ValueError(f"{what}: vertex {i} is repeated")
        if math.dist(pts[i], pts[(i + 1) % n]) < MIN_EDGE_FT:
            raise ValueError(f"{what}: edge {i} is shorter than {MIN_EDGE_FT} ft")
    if not all(math.isfinite(c) for p in pts for c in p):
        raise ValueError(f"{what}: has a non-finite coordinate")
    poly = Polygon(pts)
    if not poly.is_valid or not poly.exterior.is_simple:
        raise ValueError(f"{what}: the outline crosses or touches itself; pick a simpler polygon or other "
                         "gable_edges, or call rect_fit first")
    if _signed_area(pts) <= MIN_AREA_SQFT:
        raise ValueError(f"{what}: the outline is clockwise or has an area under {MIN_AREA_SQFT} sqft")


def safe_extension(poly: list[Pt], gable_idx: set[int], dist: float,
                   extend: Callable[[list[Pt], set[int], float], list[Pt]]) -> tuple[list[Pt], float]:
    """``(ring, d)``: ``extend(poly, gable_idx, d)`` for the largest ``d`` in ``dist, dist/2, ...`` (down to the
    outline's extent) whose ring passes :func:`check_ring`. ``d != dist`` means the extension was shortened (the
    caller records a note). Raises ValueError when no distance gives a valid ring.
    """
    x0, y0, x1, y1 = Polygon(poly).bounds
    floor = max(x1 - x0, y1 - y0)
    d = dist
    while True:
        ring = extend(poly, gable_idx, d)
        try:
            check_ring(ring, "extended outline")
            return ring, d
        except ValueError:
            pass
        if d <= floor * 1.01:
            raise ValueError("gable edges cannot be extended on this outline (the sides next to a gable end "
                             "converge); call rect_fit first or choose other gable_edges")
        d = max(d / 2, floor)
