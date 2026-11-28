"""The data one measurement carries from the data stages to the model: address, frame, outline, LiDAR facts.

Holds no blocks (the plane engine works on points); the name stays because the pipeline, the lot and the
adapter pass this object around.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Pt = tuple[float, float]


@dataclass
class BlockSet:
    address: dict[str, Any]
    origin: dict[str, float]
    frame: dict[str, Any]
    footprint_ft: list[Pt]
    footprint_meta: dict[str, Any] = field(default_factory=dict)
    lidar: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
