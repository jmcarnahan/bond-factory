"""Measured positions for ``planes_envelope_lines`` (internal): where two raw clusters touch is a measurement of the
line between them (at 2-5/12 a 0.3 ft height error moves a computed intersection 1-2 ft), and lines of one roof
line that the data splits (a ridge across a seam, a cross gable's top edge dying into the main ridge) are made one.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry.base import BaseGeometry

from .planes_envelope_geom import Eq, ang_diff

TOUCH_FT = 2.0  # two clusters this close measure the border between them
ALIGN_FT = 2.5  # parallel lines of one face against two same-facing planes closer than this become one line  # a shorter shared border between planes at different heights draws no step line


def touch_points(ri: BaseGeometry, rj: BaseGeometry, tol: float = TOUCH_FT, step: float = 0.5) -> list[tuple[float, float]]:
    """The measured border of two clusters: midpoints between their outlines wherever they come within ``tol``."""
    from shapely.ops import nearest_points

    out = []
    for a, b in ((ri, rj), (rj, ri)):
        for part in getattr(a, "geoms", [a]):
            if part.geom_type != "Polygon":
                continue
            ring = part.exterior
            for k in range(int(ring.length / step)):
                p = ring.interpolate(k * step)
                if b.distance(p) <= tol:
                    q = nearest_points(b, p)[0]
                    out.append(((p.x + q.x) / 2, (p.y + q.y) / 2))
    return out


def _offset(p: tuple[float, float], line: tuple[tuple[float, float], tuple[float, float]]) -> float:
    (cx, cy), (dx, dy) = line
    return -dy * (p[0] - cx) + dx * (p[1] - cy)


def _shifted(line: tuple[tuple[float, float], tuple[float, float]], m: float) -> tuple[tuple[float, float], tuple[float, float]]:
    (cx, cy), (dx, dy) = line
    return (cx - dy * m, cy + dx * m), (dx, dy)


def _ordered(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Points sorted along their main direction (so a step fit sees them as one border from end to end)."""
    mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    t = 0.5 * math.atan2(2 * sxy, sxx - syy)
    return sorted(pts, key=lambda p: p[0] * math.cos(t) + p[1] * math.sin(t))


def _align(recs: list[dict[str, Any]], eqs: list[Eq]) -> None:
    """Meet lines of one face against two planes that face the same way (a seam between them, e.g. two north planes
    of different pitch) are one roof line: parallel lines less than ``ALIGN_FT`` apart take their mean position."""
    for x, r1 in enumerate(recs):
        for r2 in recs[x + 1:]:
            if r1["kind"] != "meet" or r2["kind"] != "meet":
                continue
            common = set(r1["fa"]) & set(r2["fb"]) or set(r1["fb"]) & set(r2["fa"]) or set(r1["fa"]) & set(r2["fa"]) \
                or set(r1["fb"]) & set(r2["fb"])
            if not common:
                continue
            o1 = [k for k in r1["fa"] + r1["fb"] if k not in common]
            o2 = [k for k in r2["fa"] + r2["fb"] if k not in common]
            if _facing_deg(eqs[o1[0]], eqs[o2[0]]) >= 45.0:
                continue
            (p1, d1), (p2, d2) = r1["lines"][0], r2["lines"][0]
            if ang_diff(math.degrees(math.atan2(d1[1], d1[0])), math.degrees(math.atan2(d2[1], d2[0]))) > 1.0:
                continue
            gap = _offset(p2, (p1, d1))
            if abs(gap) > ALIGN_FT:
                continue
            w1, w2 = len(r1["touch"]) + 1, len(r2["touch"]) + 1
            mid = gap * w2 / (w1 + w2)  # from line 1 toward line 2, weighted by how much measured border each has
            r1["lines"] = [_shifted((p1, d1), mid)]
            r2["lines"] = [_shifted((p1, d1), mid)]
            r1["aligned"] = r2["aligned"] = True


def _step_onto_meet(recs: list[dict[str, Any]]) -> None:
    """A straight step that runs parallel to, and less than ``ALIGN_FT`` from, an intersection line of one of its two
    planes is that line continued (a cross gable's top edge dying into the main ridge): it takes the line's position
    so the borders meet in one point instead of leaving a notch."""
    for st in recs:
        if st["kind"] != "step" or len(st["lines"]) != 1:
            continue
        ps, ds = st["lines"][0]
        best = None
        for mt in recs:
            if mt["kind"] != "meet" or not (set(mt["fa"] + mt["fb"]) & set(st["fa"] + st["fb"])):
                continue
            pm, dm = mt["lines"][0]
            if ang_diff(math.degrees(math.atan2(ds[1], ds[0])), math.degrees(math.atan2(dm[1], dm[0]))) > 1.0:
                continue
            gap = _offset(pm, (ps, ds))
            if abs(gap) <= ALIGN_FT and (best is None or abs(gap) < abs(best)):
                best = gap
        if best is not None:
            st["lines"] = [_shifted((ps, ds), best)]
            st["aligned"] = True


def _facing_deg(e1: Eq, e2: Eq) -> float:
    g1, g2 = math.hypot(e1[0], e1[1]), math.hypot(e2[0], e2[1])
    if g1 < 1e-6 or g2 < 1e-6:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (e1[0] * e2[0] + e1[1] * e2[1]) / (g1 * g2)))))
