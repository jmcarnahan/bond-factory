"""Planning tools for the agent: where the roof sections are, where to cut between them, and how a draft scores.

A roof like a house with a high front section and a lower rear section is decided by HEIGHT first and ridge lines
second: ``levels`` groups the LiDAR segments by height above ground; ``split_between`` finds the straight cut that
best separates two groups (a cut along the building's own directions); ``check_draft`` scores a draft of blocks
against the measured planes with the pipeline's own harness. All three add to ``Workspace`` (mixin); every number
they return is citable by the agent like any tool result.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .agent_draft import score_draft
from .classify import polygons_of
from .ringgeom import split_footprint

LEVEL_GAP_FT = 1.5  # sorted segment heights closer than this belong to one level (a hip's faces differ by < 1 ft)
CUT_ANGLES_DEG = tuple(range(-12, 13, 3))  # tilts tried either side of each of the building's two main directions
CUT_STEP_FT = 0.5
BIG = 1e4
OPEN_FT = 1.0  # clean_outline removes parts of a section narrower than twice this
OPEN_KEEP = 0.9  # ... unless that would lose more than 10 percent of its area
RECT_REACH_FT = 1.0  # a fitted rectangle may overshoot its section by at most this


def _cluster_heights(items: list[tuple[str, float]], gap: float = LEVEL_GAP_FT) -> list[list[str]]:
    """Single-linkage groups of ``(id, height)`` on the height axis, lowest group first."""
    out: list[list[str]] = []
    last = None
    for sid, h in sorted(items, key=lambda t: t[1]):
        if last is None or h - last > gap:
            out.append([])
        out[-1].append(sid)
        last = h
    return out


class PlanTools:
    """Mixin for ``Workspace``: needs ``rows``, ``segment_polys``, ``footprint``, ``_poly``, ``_new``, ``finalize``."""

    blockset: Any = None
    _planes: list[Any] | None = None

    def _seg_union(self, ids: list[str], within: Polygon) -> Polygon:
        shapes = []
        for r in self._seg(ids):  # type: ignore[attr-defined]
            sp = self.segment_polys.get(r["id"]) or box(*r["bbox_ft"])  # type: ignore[attr-defined]
            shapes.append(sp.buffer(0).intersection(within))
        return unary_union([s for s in shapes if not s.is_empty])

    # --- tools
    def levels(self) -> dict[str, Any]:
        """Height levels of the sloped segments (lowest first) and of the flat ones, with what each level contains."""
        rows = [r for r in self.rows.values() if r.get("height_ft") is not None]  # type: ignore[attr-defined]
        if not rows:
            raise ValueError("this evidence has no heights; decide from azimuths and use region_from_segments")
        out: dict[str, Any] = {}
        for kind, label in (("sloped", "sloped_levels"), ("flat", "flat_levels")):
            part = [r for r in rows if r["form_hint"] == kind]
            groups = []
            for ids in _cluster_heights([(r["id"], r["height_ft"]) for r in part]):
                rs = [self.rows[i] for i in ids]  # type: ignore[attr-defined]
                area = sum(r["ground_area_sqft"] for r in rs)
                shape = unary_union([self.segment_polys.get(i) or box(*self.rows[i]["bbox_ft"])  # type: ignore[attr-defined]
                                     for i in ids])
                g: dict[str, Any] = {"segment_ids": ids, "ground_area_sqft": area,
                                     "height_ft_min": min(r["height_ft"] for r in rs),
                                     "height_ft_max": max(r["height_ft"] for r in rs),
                                     "bbox_ft": list(shape.bounds)}
                if kind == "sloped":
                    g["pitch_rise"] = sum(r["pitch_rise"] * r["ground_area_sqft"] for r in rs) / (area or 1.0)
                    g["azimuths_deg"] = sorted({round(float(r["azimuth_deg"]), 1) for r in rs if r["azimuth_deg"] is not None})
                groups.append(g)
            out[label] = groups
        out["hint"] = ("Two sloped levels = two roof sections at different heights: split_between the levels first, "
                       "then decide each section's form from its own azimuths.")
        return out

    def split_between(self, segment_ids_a: list[str], segment_ids_b: list[str], polygon_id: str = "footprint"
                      ) -> dict[str, Any]:
        """The straight cut through a polygon that best separates the segments of group a from group b."""
        poly = Polygon(self._poly(polygon_id))  # type: ignore[attr-defined]
        if set(segment_ids_a) & set(segment_ids_b):
            raise ValueError("a segment cannot be on both sides of the cut")
        a, b = self._seg_union(segment_ids_a, poly), self._seg_union(segment_ids_b, poly)
        if a.is_empty or b.is_empty:
            raise ValueError("a group has no area inside this polygon")
        rect = poly.minimum_rotated_rectangle
        c = list(rect.exterior.coords)
        base = math.degrees(math.atan2(c[1][1] - c[0][1], c[1][0] - c[0][0]))
        cx, cy = poly.centroid.x, poly.centroid.y
        best: tuple[float, float, float, bool] | None = None  # (cost, angle, offset, a_on_negative_side)
        for axis in (0.0, 90.0):
            for tilt in CUT_ANGLES_DEG:
                ang = math.radians(base + axis + tilt)
                ux, uy = math.cos(ang), math.sin(ang)  # the cut's direction
                nx, ny = -uy, ux  # its normal
                proj = [(x - cx) * nx + (y - cy) * ny for x, y in poly.exterior.coords]
                off = min(proj) - CUT_STEP_FT
                while off <= max(proj) + CUT_STEP_FT:
                    neg = _half(cx, cy, ux, uy, nx, ny, off, -1)
                    pos = _half(cx, cy, ux, uy, nx, ny, off, 1)
                    for a_neg in (True, False):
                        wrong = (a.intersection(pos).area + b.intersection(neg).area if a_neg
                                 else a.intersection(neg).area + b.intersection(pos).area)
                        if best is None or wrong < best[0] - 1e-9:
                            best = (wrong, ang, off, a_neg)
                    off += CUT_STEP_FT
        if best is None:
            raise ValueError("no cut could be tried on this polygon")
        wrong, ang, off, a_neg = best
        ux, uy, nx, ny = math.cos(ang), math.sin(ang), -math.sin(ang), math.cos(ang)
        p0 = (cx + nx * off, cy + ny * off)
        line = [[p0[0], p0[1]], [p0[0] + ux * 10.0, p0[1] + uy * 10.0]]
        parts = split_footprint(self._poly(polygon_id), line)  # type: ignore[attr-defined]
        sides: dict[bool, list[Polygon]] = {True: [], False: []}
        for part in parts:
            pp = Polygon(part["polygon"])
            side_neg = (pp.centroid.x - p0[0]) * nx + (pp.centroid.y - p0[1]) * ny < 0
            sides[side_neg == a_neg].append(pp)  # True: the a side
        res: dict[str, Any] = {"line_ft": line, "bearing_deg": (90.0 - math.degrees(ang)) % 180.0,
                               "misplaced_sqft": wrong}
        for key, group in (("a", sides[True]), ("b", sides[False])):
            if not group:
                raise ValueError("the cut leaves one side empty; choose other segment groups")
            merged = unary_union(group)
            big = max(polygons_of(merged), key=lambda g: g.area)
            from .classify import ring_of

            pid = self._new(ring_of(big, 0.0))  # type: ignore[attr-defined]
            res[key] = {"polygon_id": pid, "area_sqft": big.area, "bounds": list(big.bounds)}
        return res

    def clean_outline(self, polygon_id: str) -> dict[str, Any]:
        """A simpler outline for a section: tails and spikes removed, a rectangle when within 10 percent of one."""
        from .classify import _fit_ring, clean_polygon, largest, ring_of

        part = Polygon(self._poly(polygon_id))  # type: ignore[attr-defined]
        opened = largest(part.buffer(-OPEN_FT, join_style=2).buffer(OPEN_FT, join_style=2))  # drops tails and jogs narrower than 2 * OPEN_FT
        base = opened if opened is not None and opened.area >= OPEN_KEEP * part.area else part
        ring, extra = _fit_ring(clean_polygon(base), Polygon(self.footprint), [])  # type: ignore[attr-defined]
        poly = Polygon(ring).buffer(0)
        rect = not any("simplified polygon" in e for e in extra)
        if rect:  # a rectangle never reaches further than the section it came from (a cut stays a cut)
            poly = largest(poly.intersection(part.buffer(RECT_REACH_FT))) or poly
        pid = self._new(ring_of(poly.simplify(0.1), 0.0))  # type: ignore[attr-defined]
        new = Polygon(self.polys[pid])  # type: ignore[attr-defined]
        return {"polygon_id": pid, "area_sqft": new.area, "original_area_sqft": part.area,
                "bounds": list(new.bounds), "n_vertices": len(self.polys[pid]),  # type: ignore[attr-defined]
                "kept": "rectangle" if rect else "simplified outline", "notes": extra}

    def check_draft(self, blocks: list[dict[str, Any]]) -> dict[str, Any]:
        """Score a draft (the same ``blocks`` list ``finalize`` takes) against the measured planes."""
        if self.blockset is None or not self.blockset.blocks:
            raise ValueError("check_draft needs LiDAR blocks; this evidence has none")
        if self._planes is None:
            from .planes import snap_with_stats

            snap = snap_with_stats(self.blockset)
            if snap.failed or not snap.planes:
                raise ValueError("the measured planes could not be snapped; use your own judgement and finalize")
            self._planes = snap.planes
        rbs, _decisions, _warnings = self.finalize({"blocks": blocks})  # type: ignore[attr-defined]
        return score_draft(rbs, self.blockset, self._planes, {"method": "lidar_agent"})


def _half(cx: float, cy: float, ux: float, uy: float, nx: float, ny: float, off: float, side: int) -> Polygon:
    """The half plane on one side (``side`` -1 or 1) of the line through (cx,cy)+n*off with direction u, as a box."""
    ox, oy = cx + nx * off, cy + ny * off
    s = side * BIG
    return Polygon([(ox - ux * BIG, oy - uy * BIG), (ox + ux * BIG, oy + uy * BIG),
                    (ox + ux * BIG + nx * s, oy + uy * BIG + ny * s), (ox - ux * BIG + nx * s, oy - uy * BIG + ny * s)])
