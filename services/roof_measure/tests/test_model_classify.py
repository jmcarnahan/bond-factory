"""Classification of the hand-crafted site 1 blocks and of small synthetic block sets."""

import pytest
from shapely.geometry import Polygon

from roof_measure.classify import Block, BlockSet, classify_blocks, decide_form, tile_to_footprint


@pytest.fixture(scope="module")
def site1_cls(handmade_blocks_path):
    bs = BlockSet.load(handmade_blocks_path)
    return bs, classify_blocks(bs)


def test_hip_detected_with_four_facets_and_pitch(site1_cls):
    _bs, cl = site1_cls
    hips = [b for b in cl.blocks if b.form == "hip"]
    assert len(hips) == 1
    assert 3.8 <= hips[0].pitch_rise <= 4.0
    assert hips[0].poly.centroid.x < 40  # west end
    assert sorted(hips[0].source_blocks) == ["k4", "k5", "k6", "k7"]


def test_three_awnings_on_the_south_outline(site1_cls):
    bs, cl = site1_cls
    sheds = [b for b in cl.blocks if b.form == "shed"]
    assert len(sheds) == 3
    ymin = bs.footprint.bounds[1]
    for s in sheds:
        assert s.aspect_deg == pytest.approx(180)
        assert s.poly.bounds[1] < ymin + 10 and s.poly.area < 120


def test_blocks_tile_the_footprint(site1_cls):
    bs, cl = site1_cls
    fp = bs.footprint
    union = Polygon().union(cl.blocks[0].poly)
    for b in cl.blocks[1:]:
        union = union.union(b.poly)
    assert union.intersection(fp).area / fp.area > 0.99
    assert sum(b.poly.area for b in cl.blocks) < union.area * 1.07  # no real overlaps
    assert cl.gap_filled_pct > 5
    assert any("assigned to the nearest flat block" in n for n in cl.notes)


def test_flats_merge_only_when_simple(handmade_blocks_path):
    bs = BlockSet.load(handmade_blocks_path)
    merged = classify_blocks(bs, merge_flats=True)
    apart = classify_blocks(bs)
    assert len([b for b in apart.blocks if b.form == "flat"]) >= len([b for b in merged.blocks if b.form == "flat"]) >= 1


def test_decide_form_by_aspects():
    assert decide_form([(178, 1), (269, 1), (86, 1), (356, 1)])[0] == "hip"
    assert decide_form([(0, 5), (180, 5)])[0] == "gable"
    assert decide_form([(180, 5), (183, 2)])[0] == "shed"


def test_gable_from_two_opposite_faces():
    ring = [(0, 0), (40, 0), (40, 24), (0, 24)]
    bs = BlockSet(address={}, origin={"lat": 0, "lng": 0}, frame={}, footprint_ft=ring)
    bs.blocks = [
        Block("k0", "sloped", [(0, 0), (40, 0), (40, 12), (0, 12)], 480, 20, 20, 6.0, 180.0),
        Block("k1", "sloped", [(0, 12), (40, 12), (40, 24), (0, 24)], 480, 20, 20, 6.0, 0.0),
    ]
    cl = classify_blocks(bs)
    assert [b.form for b in cl.blocks] == ["gable"]
    g = cl.blocks[0]
    assert len(g.gable_edges) == 2 and g.pitch_rise == pytest.approx(6.0)
    assert g.ridge_azimuth_deg == pytest.approx(90, abs=1)


def test_tiling_gives_gaps_to_nearest_block():
    fp = Polygon([(0, 0), (20, 0), (20, 10), (0, 10)])
    a = Polygon([(0, 0), (8, 0), (8, 10), (0, 10)])
    b = Polygon([(12, 0), (20, 0), (20, 10), (12, 10)])
    out, frac = tile_to_footprint({"a": a, "b": b}, fp)
    assert frac == pytest.approx(0.2)
    assert out["a"].area == pytest.approx(100, abs=1) and out["b"].area == pytest.approx(100, abs=1)


def test_real_site1_blocks(site1_blocks_path):
    """The svc-data file: hip found, the awning is a rectangle, the interior low slope becomes flat."""
    bs = BlockSet.load(site1_blocks_path)
    cl = classify_blocks(bs)
    forms = sorted(b.form for b in cl.blocks)
    assert forms.count("hip") == 1 and forms.count("shed") == 1 and forms.count("flat") == 3
    hip = next(b for b in cl.blocks if b.form == "hip")
    assert 3.7 <= hip.pitch_rise <= 4.0
    assert any("Low-slope area inside the flat roof" in n and "2.5/12" in n for n in cl.notes)
    for s in (b for b in cl.blocks if b.form == "shed"):
        assert len(s.polygon) == 4 and s.poly.area < 200


def test_real_hip_is_a_four_facet_rectangle_near_truth(site1_blocks_path):
    from roof_measure.skeleton import hip_roof_edges, rect_fit

    cl = classify_blocks(BlockSet.load(site1_blocks_path))
    hip = next(b for b in cl.blocks if b.form == "hip")
    assert len(hip.polygon) == 4 and len(hip_roof_edges(hip.polygon, hip.pitch_rise)["facets"]) == 4
    assert 900 < hip.poly.area < 1150
    assert 25 <= rect_fit(hip.polygon)[1] <= 31.0  # short side (30.2 on the 13:07 blocks)
    flats = [b for b in cl.blocks if b.form == "flat"]
    assert len(flats) == 3  # svc-data's flat blocks stay separate


def test_ragged_gable_house_gets_two_gable_ends():
    """Live regression (1528 W 223rd St): a ragged union must not turn every short edge into a gable end."""
    ring = [(0, 0), (2, -1), (30, 0), (31, 2), (30, 40), (14, 42), (6, 41), (0, 38), (1, 20)]
    bs = BlockSet(address={}, origin={"lat": 0, "lng": 0}, frame={}, footprint_ft=ring)
    bs.blocks = [
        Block("k0", "sloped", [(1, 1), (15, 1), (15, 40), (1, 38)], 540, 20, 20, 3.2, 90.0),
        Block("k1", "sloped", [(15, 1), (30, 1), (30, 40), (15, 40)], 585, 20, 20, 3.2, 270.0),
    ]
    g = classify_blocks(bs).blocks[0]
    assert g.form == "gable" and len(g.gable_edges) == 2
