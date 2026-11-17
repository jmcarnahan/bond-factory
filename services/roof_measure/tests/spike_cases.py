"""Synthetic jagged hip blocks (invented 40 x 24 ft frame) whose straight skeleton has a spike facet."""

from __future__ import annotations

import json
from pathlib import Path

from roof_measure import model as model_mod
from roof_measure.classify import RoofBlock
from roof_measure.synth import _plain_blockset

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FOOTPRINT = [(0.0, 0.0), (40.0, 0.0), (40.0, 24.0), (0.0, 24.0)]
FIXABLE = ("jagged_hip_spike_a", "jagged_hip_spike_b")  # a spike facet under the bounds: merged into a neighbour
UNFIXABLE = "jagged_hip_unfixable"  # the spike facet is not a sliver: validate still rejects the model


def roof_block(name: str) -> RoofBlock:
    d = json.loads((FIXTURES / f"{name}.json").read_text())
    return RoofBlock(id="b1", form=d["form"], polygon=[tuple(p) for p in d["polygon"]], pitch_rise=d["pitch_rise"],
                     ridge_azimuth_deg=90.0, level_ft=0.0, eave_height_ft=10.0)


def build(name: str) -> dict:
    return model_mod.build_model(_plain_blockset("t", FOOTPRINT), [roof_block(name)], {"method": "lidar_skeleton"}, None)
