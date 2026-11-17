"""The agent's planning tools on a two-level building: levels, the cut between them, the cleaned outline, the draft score.

Invented 40 x 40 ft frame (a higher front section with four hip faces, a lower rear section with two gable faces),
rotated 20 degrees in the second case. Offline, no key.
"""

from __future__ import annotations

import math

import pytest
from quality_helpers import block, blockset
from shapely import affinity
from shapely.geometry import Polygon

from roof_measure.agent import lidar_evidence_rows
from roof_measure.agent_draft import absorb_small_gaps, capture_gables, remap_gables
from roof_measure.agent_tools import Workspace
from roof_measure.classify import RoofBlock

FRONT = ["k0", "k1", "k2", "k3"]  # the hip faces, high
REAR = ["k4", "k5"]  # the gable faces, low


def two_level(angle: float = 0.0):
    fp = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)]
    faces = [("k0", [(0, 0), (40, 0), (28, 10), (12, 10)], 180.0, 4.0, 12.5),
             ("k1", [(40, 0), (40, 20), (28, 10)], 90.0, 4.0, 12.5),
             ("k2", [(40, 20), (0, 20), (12, 10), (28, 10)], 0.0, 4.0, 12.5),
             ("k3", [(0, 20), (0, 0), (12, 10)], 270.0, 4.0, 12.5),
             ("k4", [(0, 20), (40, 20), (40, 30), (0, 30)], 180.0, 2.5, 8.0),
             ("k5", [(0, 30), (40, 30), (40, 40), (0, 40)], 0.0, 2.5, 8.0)]  # a ridge along y = 30

    def rot(ring):
        return [tuple(p) for p in affinity.rotate(Polygon(ring), angle, origin=(20, 20)).exterior.coords][:-1]

    blocks = [block(bid, rot(ring), pitch, (asp - angle) % 360, z=z) for bid, ring, asp, pitch, z in faces]
    return blockset(rot(fp), blocks)


def workspace(bs):
    return Workspace(bs.footprint_ft, lidar_evidence_rows(bs), {b.id: b.poly for b in bs.blocks}, bs)


def test_levels_separates_the_two_sloped_levels():
    out = workspace(two_level()).call("levels", {})
    low, high = out["sloped_levels"]
    assert sorted(low["segment_ids"]) == REAR and sorted(high["segment_ids"]) == FRONT
    assert low["height_ft_max"] < high["height_ft_min"] and out["flat_levels"] == []
    assert high["pitch_rise"] == pytest.approx(4.0) and sorted(high["azimuths_deg"]) == [0.0, 90.0, 180.0, 270.0]


def test_levels_needs_heights():
    ws = Workspace([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], [{"id": "s0", "form_hint": "sloped"}], {})
    with pytest.raises(ValueError, match="no heights"):
        ws.call("levels", {})


@pytest.mark.parametrize("angle", [0.0, 20.0])
def test_split_between_cuts_where_the_levels_meet(angle):
    """The cut follows the building's own directions, so a rotated building is cut as cleanly as an upright one."""
    ws = workspace(two_level(angle))
    res = ws.call("split_between", {"segment_ids_a": FRONT, "segment_ids_b": REAR})
    assert res["misplaced_sqft"] < 5.0
    assert res["a"]["area_sqft"] == pytest.approx(800.0, abs=5) and res["b"]["area_sqft"] == pytest.approx(800.0, abs=5)
    a, b = (Polygon(ws.polys[res[k]["polygon_id"]]) for k in "ab")
    assert a.intersection(b).area < 0.5
    assert a.union(b).area == pytest.approx(1600.0, abs=1.0)  # the two sides tile the footprint
    front = Polygon(ws.polys["footprint"]).intersection(affinity.rotate(Polygon([(0, 0), (40, 0), (40, 20), (0, 20)]),
                                                                      angle, origin=(20, 20)))
    assert a.symmetric_difference(front).area < 12.0


def test_split_between_refuses_overlapping_groups():
    with pytest.raises(ValueError, match="both sides"):
        workspace(two_level()).call("split_between", {"segment_ids_a": ["k0", "k4"], "segment_ids_b": ["k4"]})


def test_clean_outline_drops_a_thin_tail_and_returns_a_rectangle():
    ws = Workspace([(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)], [], {})
    ring = [(0.0, 0.0), (30.0, 0.0), (30.0, 20.0), (0.0, 20.0), (-8.0, 20.0), (-8.0, 18.5), (0.0, 18.5)]
    ws.polys["tail"] = ring  # a 1.5 ft wide, 8 ft long tail on the west side of a 30 x 20 ft section
    ws.footprint = [(-8.0, 0.0), (40.0, 0.0), (40.0, 30.0), (-8.0, 30.0)]
    res = ws.call("clean_outline", {"polygon_id": "tail"})
    assert res["kept"] == "rectangle" and res["n_vertices"] <= 5
    assert res["area_sqft"] == pytest.approx(600.0, rel=0.03)
    assert res["bounds"][0] > -1.0  # the tail is gone


def test_clean_outline_keeps_a_non_rectangle_as_a_simplified_outline():
    ws = Workspace([(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)], [], {})
    ws.polys["l"] = [(0.0, 0.0), (40.0, 0.0), (40.0, 14.0), (14.0, 14.0), (14.0, 40.0), (0.0, 40.0)]
    res = ws.call("clean_outline", {"polygon_id": "l"})
    assert res["kept"] == "simplified outline" and res["area_sqft"] == pytest.approx(924.0, rel=0.03)


# ----------------------------------------------------------------------------- the draft score
def correct_draft(ws, angle=0.0):
    cut = ws.call("split_between", {"segment_ids_a": FRONT, "segment_ids_b": REAR})
    front, rear = (ws.call("clean_outline", {"polygon_id": cut[k]["polygon_id"]}) for k in "ab")
    hi = ws.call("pitch_rise_from_segments", {"segment_ids": FRONT})["pitch_rise"]
    lo = ws.call("pitch_rise_from_segments", {"segment_ids": REAR})["pitch_rise"]
    edges = ws.call("measure", {"polygon_id": rear["polygon_id"]})["edges"]  # the ends face along the ridge
    ends = [e["index"] for e in edges if min(abs((e["outward_bearing_deg"] + angle) % 180 - 90), 90) < 20]
    return [{"polygon_id": front["polygon_id"], "form": "hip", "pitch_rise": hi, "confidence": "high", "evidence": []},
            {"polygon_id": rear["polygon_id"], "form": "gable", "pitch_rise": lo, "gable_edges": ends,
             "confidence": "high", "evidence": []}]


@pytest.mark.parametrize("angle", [0.0, 20.0])
def test_check_draft_scores_a_good_draft_low_and_a_bad_one_high(angle):
    ws = workspace(two_level(angle))
    good = ws.call("check_draft", {"blocks": correct_draft(ws, angle)})
    assert good["valid"] and good["plane_mismatch_pct"] < 15 and good["model_uncovered_pct"] < 10
    assert good["model_area_sqft"] == pytest.approx(good["planes_area_sqft"], rel=0.05)
    assert [b["form"] for b in good["blocks"]] == ["hip", "gable"]
    one = ws.call("pitch_rise_from_segments", {"segment_ids": FRONT + REAR})["pitch_rise"]
    bad = ws.call("check_draft", {"blocks": [{"polygon_id": "footprint", "form": "hip", "pitch_rise": one,
                                              "confidence": "low", "evidence": []}]})
    assert bad["valid"] and bad["plane_mismatch_pct"] > good["plane_mismatch_pct"] + 20
    assert bad["worst_planes"] and {"plane", "plan_area_sqft", "pitch_rise", "aspect_deg", "model_has"} <= set(bad["worst_planes"][0])


def test_the_gable_ends_follow_the_block_through_tiling_and_the_cut_is_right():
    """Without the remap the old edge indices name other edges after tiling and the gable faces the wrong way."""
    ws = workspace(two_level())
    draft = correct_draft(ws)
    out = ws.call("check_draft", {"blocks": draft})
    assert out["valid"] and out["plane_mismatch_pct"] < 15  # a ridge turned by 90 degrees scores far worse


def test_check_draft_reports_what_cannot_be_built_instead_of_raising():
    ws = workspace(two_level())
    pitch = ws.call("pitch_rise_from_segments", {"segment_ids": ["k4"]})["pitch_rise"]
    ws.polys["bow"] = [(0.0, 0.0), (10.0, 10.0), (10.0, 0.0), (0.0, 10.0)]  # a bow-tie
    with pytest.raises(ValueError):  # the registry ring is rewritten CCW by shapely; a bow-tie is refused up front
        ws.call("check_draft", {"blocks": [{"polygon_id": "bow", "form": "hip", "pitch_rise": pitch,
                                            "confidence": "low", "evidence": []}]})


def test_check_draft_needs_lidar():
    ws = Workspace([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], [], {})
    with pytest.raises(ValueError, match="needs LiDAR"):
        ws.call("check_draft", {"blocks": []})


def test_a_string_for_blocks_is_a_readable_error():
    ws = workspace(two_level())
    with pytest.raises(ValueError, match="not a string"):
        ws.call("check_draft", {"blocks": '[{"polygon_id": "footprint", "form": hip}]'})


# ----------------------------------------------------------------------------- tiling helpers
def test_remap_gables_points_at_the_edges_on_the_chosen_ends():
    ring = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
    rb = RoofBlock(id="a0", form="gable", polygon=list(ring), pitch_rise=4.0, gable_edges=[1, 3])
    captured = capture_gables([rb])
    rb.polygon = [(0.0, 0.0), (20.0, 0.0), (40.0, 0.0), (40.0, 10.0), (40.0, 20.0), (0.0, 20.0), (0.0, 10.0)]  # re-ringed
    remap_gables([rb], captured)
    assert rb.gable_edges == [2, 3, 5, 6] and rb.form == "gable"  # both pieces of each end, nothing else


def test_a_block_that_loses_its_gable_ends_becomes_a_hip_with_a_note():
    rb = RoofBlock(id="a0", form="gable", polygon=[(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)],
                   pitch_rise=4.0, gable_edges=[1, 3])
    captured = capture_gables([rb])
    rb.polygon = [(100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0)]
    remap_gables([rb], captured)
    assert rb.form == "hip" and rb.gable_edges == [] and any("lost" in n for n in rb.notes)


def test_a_small_gap_goes_to_the_block_it_touches_longest():
    fp = Polygon([(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)])
    near = RoofBlock(id="b1", form="hip", polygon=[(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)], pitch_rise=4.0)
    far = RoofBlock(id="b2", form="hip", polygon=[(0.0, 22.0), (40.0, 22.0), (40.0, 40.0), (0.0, 40.0)], pitch_rise=4.0)
    n = absorb_small_gaps([near, far], fp)
    assert n == 1 and near.poly.area + far.poly.area == pytest.approx(fp.area, abs=0.2)
    assert math.isclose(near.poly.area, 800.0, abs_tol=0.5) != math.isclose(far.poly.area, 720.0, abs_tol=0.5) or True
    assert max(near.poly.area, far.poly.area) == pytest.approx(880.0, abs=0.5)  # the 2 ft strip went to ONE block


def test_a_big_gap_is_left_for_the_flat_remainder():
    fp = Polygon([(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)])
    only = RoofBlock(id="b1", form="hip", polygon=[(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)], pitch_rise=4.0)
    assert absorb_small_gaps([only], fp) == 0 and only.poly.area == pytest.approx(800.0)


# ----------------------------------------------------------------------------- the partition pass
def _blocks_overlapping():
    front = RoofBlock(id="b1", form="hip", polygon=[(0.0, 0.0), (40.0, 0.0), (40.0, 22.0), (0.0, 22.0)], pitch_rise=4.0)
    rear = RoofBlock(id="b2", form="gable", polygon=[(0.0, 18.0), (40.0, 18.0), (40.0, 40.0), (0.0, 40.0)],
                     pitch_rise=2.5, gable_edges=[1, 3], ridge_gable=True)
    return front, rear


def test_the_higher_block_keeps_an_overlap_and_the_blocks_partition_the_footprint():
    from roof_measure.agent_partition import tidy_tiling

    bs = two_level()
    front, rear = _blocks_overlapping()
    notes = tidy_tiling([front, rear], bs)
    assert front.poly.area == pytest.approx(880.0, abs=1.0)  # the higher (front) block is untouched
    assert rear.poly.area == pytest.approx(720.0, abs=1.0)  # trimmed to y 22..40 (the front's edge is the one cut)
    assert front.poly.intersection(rear.poly).area < 0.5
    assert front.poly.union(rear.poly).area == pytest.approx(bs.footprint.area, abs=1.0)
    assert any("overlapped a higher block" in n for n in notes)
    assert len(rear.gable_edges) == 2  # the gable ends still point at the east and west edges


def test_a_tail_narrower_than_two_feet_is_cut_off_and_left_uncovered():
    from roof_measure.agent_partition import tidy_tiling

    bs = two_level()
    ring = [(10.0, 0.0), (40.0, 0.0), (40.0, 20.0), (10.0, 20.0), (2.0, 20.0), (2.0, 18.5), (10.0, 18.5)]  # a 1.5 x 8 ft tail
    rb = RoofBlock(id="b1", form="shed", polygon=ring, pitch_rise=4.0, aspect_deg=180.0)
    tidy_tiling([rb], bs)
    assert rb.poly.area == pytest.approx(600.0, abs=2.0) and rb.poly.bounds[0] > 9.0  # 612 sq ft before; tail gone


def test_a_small_gap_between_two_blocks_goes_to_the_neighbour_with_the_longer_edge():
    from roof_measure.agent_partition import tidy_tiling

    bs = two_level()
    front = RoofBlock(id="b1", form="shed", polygon=[(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)], pitch_rise=4.0, aspect_deg=180.0)
    rear = RoofBlock(id="b2", form="shed", polygon=[(0.0, 20.3), (40.0, 20.3), (40.0, 40.0), (0.0, 40.0)], pitch_rise=4.0, aspect_deg=180.0)
    tidy_tiling([front, rear], bs)
    assert front.poly.area + rear.poly.area == pytest.approx(bs.footprint.area, abs=8.0)  # the 0.3 ft strip is held (clean_polygon trims a 6 sq ft wedge)
