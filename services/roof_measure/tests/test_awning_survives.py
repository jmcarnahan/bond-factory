"""A small shed roof (an awning) beside a flat roof survives the model's cleanup.

The proof-of-concept building lost a second awning between two weeks of results; the replay showed the cause was the
captured LiDAR data (no sloped block at that place), not the model stages. This pins the model stages' side of it:
a small shed block attached to a flat block (invented 40 x 30 ft frame, a 10 x 12 ft awning on the south side) stays a
block with a facet of its own, its eave/rake/step-flashing lengths are kept, and the sliver merge leaves it alone.
"""

from __future__ import annotations

import pytest
from quality_helpers import blockset

from roof_measure.classify import RoofBlock
from roof_measure.model import build_model, validate

FLAT = [(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)]
AWNING = [(15.0, -12.0), (25.0, -12.0), (25.0, 0.0), (15.0, 0.0)]


def model(*awnings):
    bs = blockset(FLAT, [])
    blocks = [RoofBlock(id="b1", form="flat", polygon=list(FLAT))]
    blocks += [RoofBlock(id=f"b{i + 2}", form="shed", polygon=list(ring), pitch_rise=4.0, aspect_deg=180.0)
               for i, ring in enumerate(awnings)]
    m = build_model(bs, blocks, {"method": "lidar_skeleton"})
    validate(m)
    return m


def test_a_small_shed_beside_a_flat_roof_keeps_its_block_and_facet():
    m = model(AWNING)
    assert [b["form"] for b in m["blocks"]] == ["flat", "shed"]
    shed = [f for f in m["facets"] if f["kind"] == "sloped"]
    assert len(shed) == 1 and shed[0]["plan_area_sqft"] == pytest.approx(120.0, rel=0.01)
    assert m["totals"]["pitched_area_sqft"] == pytest.approx(120.0 * (1 + (4 / 12) ** 2) ** 0.5, rel=0.01)


def test_two_awnings_are_both_kept_with_their_edges():
    second = [(28.0, -13.0), (39.0, -13.0), (39.0, 0.0), (28.0, 0.0)]
    one, two = model(AWNING), model(AWNING, second)
    assert [b["form"] for b in two["blocks"]] == ["flat", "shed", "shed"]
    assert two["totals"]["pitched_area_sqft"] > one["totals"]["pitched_area_sqft"] * 1.9
    lengths = {k: two["totals"]["lengths_ft"][k] for k in ("eave", "rake", "ridge")}
    assert lengths["rake"] > one["totals"]["lengths_ft"]["rake"] + 20.0  # the second awning's two sides
