"""What a pipeline run returns, and the verification block of a result nothing verified."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .blockset import BlockSet
from .envelope import totals_from_model


@dataclass
class PipelineResult:
    model: dict[str, Any]
    blockset: BlockSet
    paths: dict[str, Path] = field(default_factory=dict)
    method_used: str = "lidar_skeleton"
    footprint_source: str = "unknown"
    verification: dict[str, Any] = field(default_factory=dict)
    envelope: dict[str, Any] = field(default_factory=dict)
    density_pts_m2: float | None = None
    transient: bool = False  # produced by an outage fall-through: the caller must not cache it


def no_verification(model: dict[str, Any], note: str) -> dict[str, Any]:
    return {"verdict": "unverified", "notes": [note], "adjustments": [], "original_totals": totals_from_model(model),
            "model": None, "rounds": 0, "usage": {"input_tokens": 0, "output_tokens": 0}}
