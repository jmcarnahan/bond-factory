"""Shared builders for the snapping, quality and envelope-quality tests (invented coordinates only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

from roof_measure.classify import BlockSet

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SITE1 = ROOT / "fixtures" / "site1_blocks.json"
SITE1_HANDMADE = HERE / "data" / "site1_blocks_handmade.json"
TWO_LEVEL = HERE / "fixtures" / "two_level_l_blocks.json"


def block(bid: str, ring: list[tuple[float, float]], pitch: float = 4.0, aspect: float | None = 180.0,
          kind: str = "sloped", z: float = 13.0) -> dict[str, Any]:
    area = Polygon(ring).area
    return {"id": bid, "kind": kind, "polygon_ft": [list(p) for p in ring], "plan_area_sqft": round(area, 1),
            "mean_z_ft": z, "height_above_ground_ft": z - 0.4, "pitch_rise": pitch,
            "aspect_deg": None if kind == "flat" else aspect, "rms_ft": 0.1, "n_cells": int(area)}


def blockset(footprint: list[tuple[float, float]], blocks: list[dict[str, Any]]) -> BlockSet:
    return BlockSet.from_dict({
        "schema": "bond.roof_blocks/0.1", "address": {}, "origin": {"lat": 0.0, "lng": 0.0},
        "frame": {"epsg": 32631, "x0_m": 0.0, "y0_m": 0.0},
        "footprint_ft": [list(p) for p in footprint] + [list(footprint[0])],
        "footprint_meta": {"provider": "synthetic", "id": "T", "area_sqft": Polygon(footprint).area, "height_ft": 20.0},
        "lidar": {"density_per_m2": 14.0}, "blocks": blocks, "borders": [], "outline_edges": [], "extra": {}})


def hip_rectangle() -> BlockSet:
    """A 40 x 24 ft hip: four planes meeting at a ridge, the outer 0.6 ft eave strip missing (as in LiDAR)."""
    fp = [(0.0, 0.0), (40.0, 0.0), (40.0, 24.0), (0.0, 24.0)]
    inner = Polygon(fp).buffer(-0.6, join_style=2)
    faces = [("k0", [(0, 0), (40, 0), (28, 12), (12, 12)], 180.0), ("k1", [(40, 0), (40, 24), (28, 12)], 90.0),
             ("k2", [(40, 24), (0, 24), (12, 12), (28, 12)], 0.0), ("k3", [(0, 24), (0, 0), (12, 12)], 270.0)]
    blocks = []
    for bid, ring, asp in faces:
        part = Polygon(ring).intersection(inner)
        blocks.append(block(bid, [(round(x, 2), round(y, 2)) for x, y in list(part.exterior.coords)[:-1]], 4.0, asp))
    return blockset(fp, blocks)


def jittered(bs: BlockSet, sigma: float, seed: int) -> BlockSet:
    """A copy of ``bs`` with every block vertex moved by seeded Gaussian noise (ft)."""
    import random

    rng = random.Random(seed)
    d = bs.to_dict()
    for b in d["blocks"]:
        b["polygon_ft"] = [[x + rng.gauss(0, sigma), y + rng.gauss(0, sigma)] for x, y in b["polygon_ft"]]
    return BlockSet.from_dict(d)


def invariant_problems(bs: BlockSet, planes: list, clip: bool = True) -> list[str]:
    """Everything wrong with a snapped plane list (empty list: all invariants hold)."""
    import math

    from shapely.geometry import Point
    from shapely.ops import unary_union

    bad: list[str] = []
    if not planes:
        return ["no planes"]
    shapes = [p.shape() for p in planes]
    worst = max((a.intersection(b).area for i, a in enumerate(shapes) for b in shapes[i + 1:]), default=0.0)
    if worst > 0.5:
        bad.append(f"overlap {worst:.2f} sq ft")
    union = unary_union(shapes)
    if clip and abs(union.area - bs.footprint.area) > 0.01 * bs.footprint.area:
        bad.append(f"union {union.area:.0f} vs footprint {bs.footprint.area:.0f}")
    outline = bs.footprint.exterior
    for p, s in zip(planes, shapes, strict=True):
        if not (s.is_valid and s.exterior.is_simple and s.exterior.is_ccw):
            bad.append(f"{p.id} not valid/simple/ccw")
        for ring in [p.polygon, *p.holes]:
            n = len(ring)
            for i in range(n):
                a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
                v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
                cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (math.hypot(*v1) * math.hypot(*v2))
                if math.degrees(math.acos(max(-1.0, min(1.0, cos)))) < 10.0:
                    bad.append(f"{p.id} spike at {b}")
                if math.dist(b, c) < 0.5 and not (outline.distance(Point(b)) < 0.5 and outline.distance(Point(c)) < 0.5):
                    bad.append(f"{p.id} short edge at {b}")
    return bad
