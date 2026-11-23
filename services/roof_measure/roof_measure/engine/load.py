"""Read a roof-eval house folder into engine inputs (used by the CLI and the parity tools).

Layout: ``points.npy`` (n, 3) roof returns, ``points_wide.npy`` (m, 4) x, y, z, ASPRS class (optional),
``footprint.json`` ``{"polygon": [[x, y], ...]}`` and ``meta.json`` (``outline_source``, ``parcel_match``). Metres.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Polygon

from .types import RoofPoints


@dataclass
class House:
    """One house folder, read."""

    slug: str
    points: RoofPoints
    footprint: Polygon
    meta: dict[str, Any]
    wide: np.ndarray | None


def roof_points_from_arrays(xyz: np.ndarray, footprint: Polygon, wide: np.ndarray | None = None) -> RoofPoints:
    """A ``RoofPoints`` for an array of roof returns; ground comes from the class-2 returns of ``wide`` when given."""
    xyz = np.asarray(xyz, float).reshape(-1, 3)
    ground = np.zeros((0, 3))
    if wide is not None and len(wide):
        w = np.asarray(wide, float)
        ground = w[w[:, 3] == 2][:, :3]
    inside = int(shapely.contains_xy(footprint, xyz[:, 0], xyz[:, 1]).sum()) if len(xyz) else 0
    area = footprint.area
    return RoofPoints(xyz=xyz, ground_z=float(np.median(ground[:, 2])) if len(ground) else 0.0, ground_xyz=ground,
                      n_on_roof=len(xyz), n_inside=inside, density=inside / area if area else 0.0,
                      on_roof=np.ones(len(xyz), bool))


def load_house(house_dir: str | Path) -> House:
    """Read a house folder. Raises FileNotFoundError / ValueError when a required file is missing or malformed."""
    d = Path(house_dir)
    xyz = np.load(d / "points.npy").astype(float)
    wide_path = d / "points_wide.npy"
    wide = np.load(wide_path).astype(float) if wide_path.is_file() else None
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").is_file() else {}
    ring = json.loads((d / "footprint.json").read_text())["polygon"]
    footprint = Polygon(ring)
    return House(d.name, roof_points_from_arrays(xyz, footprint, wide), footprint, meta, wide)
