"""Snapped planes: disjoint, gap-free, clipped, valid, deterministic, and never an exception."""

from __future__ import annotations

import copy

import pytest
from quality_helpers import SITE1, SITE1_HANDMADE, TWO_LEVEL, block, blockset, hip_rectangle
from shapely.geometry import Polygon
from shapely.ops import unary_union

from roof_measure.classify import BlockSet
from roof_measure.planes import MIN_PLANE_SQFT, Plane, snap_planes, snap_with_stats

SOURCES = {
    "site1": lambda: BlockSet.load(SITE1),
    "site1_handmade": lambda: BlockSet.load(SITE1_HANDMADE),
    "two_level_l": lambda: BlockSet.load(TWO_LEVEL),
    "hip_rectangle": hip_rectangle,
}
SQ = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]


@pytest.fixture(params=sorted(SOURCES))
def bs(request) -> BlockSet:
    return SOURCES[request.param]()


def shapes(planes: list[Plane]) -> list[Polygon]:
    return [p.shape() for p in planes]


def overlap_sqft(planes: list[Plane]) -> float:
    s = shapes(planes)
    return max((a.intersection(b).area for i, a in enumerate(s) for b in s[i + 1:]), default=0.0)


def test_planes_do_not_overlap(bs):
    planes = snap_planes(bs, bs.footprint, clip_to_footprint=True)
    assert planes and overlap_sqft(planes) <= 0.5


def test_clipped_union_equals_the_footprint(bs):
    planes = snap_planes(bs, bs.footprint, clip_to_footprint=True)
    union = unary_union(shapes(planes))
    assert abs(union.area - bs.footprint.area) <= 0.01 * bs.footprint.area
    assert union.difference(bs.footprint.buffer(0.3)).area < 0.5  # nothing sticks out (welding moves a vertex < 0.5 ft)


def test_every_polygon_is_valid_simple_ccw_and_on_the_grid(bs):
    for clip in (True, False):
        for p in snap_planes(bs, bs.footprint, clip_to_footprint=clip):
            poly = p.shape()
            assert poly.is_valid and poly.exterior.is_simple and poly.exterior.is_ccw
            assert p.polygon[0] != p.polygon[-1]  # no repeated closing point
            assert all(round(c, 2) == c for pt in p.polygon for c in pt)
            assert poly.area >= MIN_PLANE_SQFT


def test_the_result_is_deterministic(bs):
    a = [p.to_dict() for p in snap_planes(bs, bs.footprint, clip_to_footprint=True)]
    b = [p.to_dict() for p in snap_planes(copy.deepcopy(bs), bs.footprint, clip_to_footprint=True)]
    assert a == b


def test_plane_numbers_follow_the_block(bs):
    import math

    for p in snap_planes(bs, bs.footprint, clip_to_footprint=True):
        assert p.surface_area_sqft == pytest.approx(p.plan_area_sqft / math.cos(math.atan(p.pitch_rise / 12)), abs=0.1)
        assert p.plan_area_sqft == pytest.approx(p.shape().area, abs=0.1)
        assert (p.aspect_deg is None) == (p.pitch_rise == 0.0)
        assert 0.0 <= p.filled_pct <= 100.0


def test_unclipped_planes_stay_inside_the_raw_planes():
    two = BlockSet.load(TWO_LEVEL)
    big = Polygon([(-40, -40), (120, -40), (120, 120), (-40, 120)])
    clipped = snap_planes(two, big, clip_to_footprint=True)
    free = snap_planes(two, big, clip_to_footprint=False)
    assert unary_union(shapes(clipped)).area == pytest.approx(big.area, rel=0.01)  # filled out to the huge outline
    raw = unary_union([b.poly for b in two.blocks])
    assert unary_union(shapes(free)).area < raw.buffer(2.5).area  # only the raw planes, holes closed
    assert unary_union(shapes(free)).area < 0.2 * big.area


def test_the_larger_plane_keeps_an_overlap():
    big = block("big", [(0, 0), (14, 0), (14, 20), (0, 20)], aspect=180.0)
    small = block("small", [(10, 0), (20, 0), (20, 20), (10, 20)], aspect=0.0)
    planes = {p.id: p for p in snap_planes(blockset(SQ, [small, big]), clip_to_footprint=True)}
    assert planes["big"].plan_area_sqft == pytest.approx(280.0, abs=1) and planes["small"].plan_area_sqft == pytest.approx(120.0, abs=1)
    assert planes["big"].filled_pct == 0.0 and planes["small"].filled_pct == 0.0


def test_a_gap_goes_whole_to_the_plane_that_dominates_its_border():
    # the 20 x 6 band above `wide` also touches the 4 x 4 `corner` plane: wide shares 20 ft, corner 8 ft (71%)
    wide = block("wide", [(0, 0), (20, 0), (20, 14), (0, 14)], aspect=180.0)
    corner = block("corner", [(16, 16), (20, 16), (20, 20), (16, 20)], aspect=0.0)
    planes = {p.id: p for p in snap_planes(blockset(SQ, [wide, corner]), clip_to_footprint=True)}
    assert planes["corner"].plan_area_sqft == pytest.approx(16.0, abs=0.2) and planes["corner"].filled_pct == 0.0
    assert planes["wide"].plan_area_sqft == pytest.approx(384.0, abs=1)
    assert planes["wide"].filled_pct == pytest.approx(100.0 * 104 / 384, abs=0.5)


def test_a_small_piece_is_dropped_and_its_area_is_absorbed():
    body = block("body", [(0, 0), (20, 0), (20, 20), (0, 20)], aspect=180.0)
    speck = block("speck", [(5, 5), (7, 5), (7, 7), (5, 7)], aspect=0.0)  # 4 sq ft... inside: overlap, loses
    tiny = block("tiny", [(30, 30), (31, 30), (31, 32), (30, 32)], aspect=0.0)  # 2 sq ft, outside the roof
    planes = snap_planes(blockset(SQ, [body, speck, tiny]), clip_to_footprint=True)
    assert [p.id for p in planes] == ["body"] and planes[0].plan_area_sqft == pytest.approx(400.0, abs=1)


def test_a_plane_cut_in_two_keeps_one_polygon():
    strip = block("strip", [(8, 0), (12, 0), (12, 20), (8, 20)], aspect=0.0)  # 4 x 20 wedge through the middle
    wide = block("wide", [(0, 0), (20, 0), (20, 20), (0, 20)], aspect=180.0)  # bigger: keeps everything
    planes = snap_planes(blockset(SQ, [wide, strip]), clip_to_footprint=True)
    # `wide` is larger, so `strip` loses all of its overlap and vanishes; `wide` stays whole
    assert [p.id for p in planes] == ["wide"]
    left = block("left", [(0, 0), (9, 0), (9, 20), (0, 20)], aspect=270.0)
    mid = block("mid", [(8, 8), (12, 8), (12, 12), (8, 12)], aspect=0.0)
    ring = block("ring", [(0, 0), (20, 0), (20, 20), (0, 20)], aspect=90.0, pitch=3.0)
    out = {p.id: p for p in snap_planes(blockset(SQ, [ring, left, mid]), clip_to_footprint=True)}
    assert all(isinstance(Polygon(p.polygon), Polygon) and len(p.polygon) >= 3 for p in out.values())
    assert overlap_sqft(list(out.values())) <= 0.5


def test_a_plane_plugged_into_another_gives_it_a_hole_and_the_key_is_optional():
    # a U-shaped plane with a smaller plane in its slot; the 6 ft of slot below the small plane is a gap that the
    # U dominates (12 ft of its 16 ft border), so the U closes round the small plane and has a hole
    u = block("u", [(0, 0), (8, 0), (8, 14), (12, 14), (12, 0), (20, 0), (20, 20), (0, 20)], aspect=90.0)
    plug = block("plug", [(8, 6), (12, 6), (12, 14), (8, 14)], aspect=0.0)
    planes = {p.id: p for p in snap_planes(blockset(SQ, [u, plug]), clip_to_footprint=True)}
    assert len(planes["u"].holes) == 1 and "holes" in planes["u"].to_dict()
    assert "holes" not in planes["plug"].to_dict()
    assert Polygon(planes["u"].holes[0]).area == pytest.approx(planes["plug"].plan_area_sqft, abs=0.5)
    assert overlap_sqft(list(planes.values())) <= 0.5
    assert sum(p.plan_area_sqft for p in planes.values()) == pytest.approx(400.0, abs=4)


def test_a_gap_between_several_planes_is_cut_at_the_middle():
    # a 20 x 20 outline; two 20 x 8 planes at the bottom and the top leave a 4 ft band across the middle
    low = block("low", [(0, 0), (20, 0), (20, 8), (0, 8)], aspect=180.0)
    high = block("high", [(0, 12), (20, 12), (20, 20), (0, 20)], aspect=0.0)
    planes = {p.id: p for p in snap_planes(blockset(SQ, [low, high]), clip_to_footprint=True)}
    assert planes["low"].plan_area_sqft == pytest.approx(200.0, abs=2) and planes["high"].plan_area_sqft == pytest.approx(200.0, abs=2)
    assert planes["low"].filled_pct == pytest.approx(20.0, abs=1)


def test_the_eave_strip_round_the_whole_roof_does_not_make_a_ring_plane():
    # hip_rectangle misses a 0.6 ft strip all the way round: it must be shared out, not given whole to one plane
    planes = snap_planes(hip_rectangle(), clip_to_footprint=True)
    assert len(planes) == 4 and all(not p.holes for p in planes)
    assert all(p.filled_pct < 15.0 for p in planes)


def test_plane_dict_has_exactly_the_documented_keys():
    p = snap_planes(hip_rectangle(), clip_to_footprint=True)[0].to_dict()
    assert set(p) == {"id", "polygon", "pitch_rise", "aspect_deg", "plan_area_sqft", "surface_area_sqft", "height_ft",
                      "rms_ft", "filled_pct", "straightened", "raw_plan_area_sqft", "plane_eq", "straighten_method", "section"}  # the last five are additive (0.4.0)


@pytest.mark.parametrize("make", [
    lambda: blockset(SQ, []),
    lambda: blockset([(0, 0), (1, 0), (2, 0)], [block("a", [(0, 0), (1, 0), (1, 1)])]),  # zero-area footprint
    lambda: blockset(SQ, [block("a", [(0, 0), (1, 0), (2, 0)])]),  # a line, no area
    lambda: blockset(SQ, [block("a", [(100, 100), (110, 100), (110, 110)])]),  # nowhere near the footprint
    lambda: blockset(SQ, [block("a", [(0, 0), (10, 10), (10, 0), (0, 10)])]),  # a bow-tie
])
def test_degenerate_input_never_raises(make):
    for clip in (True, False):
        planes = snap_planes(make(), clip_to_footprint=clip)
        assert isinstance(planes, list)
    assert snap_with_stats(make(), clip_to_footprint=True).planes is not None


def test_covered_pct_is_the_raw_coverage_before_gap_filling():
    left = block("left", [(0, 0), (10, 0), (10, 20), (0, 20)], aspect=270.0)  # half of the 20 x 20 outline
    res = snap_with_stats(blockset(SQ, [left]), clip_to_footprint=True)
    assert res.covered_pct == pytest.approx(50.0, abs=0.5)
    assert res.planes[0].plan_area_sqft == pytest.approx(400.0, abs=1) and res.planes[0].filled_pct == pytest.approx(50.0, abs=0.5)


def test_no_spikes_and_no_short_edges_inside_the_roof(bs):
    import math

    from shapely.geometry import Point

    outline = bs.footprint.exterior
    for p in snap_planes(bs, bs.footprint, clip_to_footprint=True):
        for ring in [p.polygon, *p.holes]:
            n = len(ring)
            for i in range(n):
                a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
                v1, v2 = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
                cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (math.hypot(*v1) * math.hypot(*v2))
                assert math.degrees(math.acos(max(-1.0, min(1.0, cos)))) >= 10.0, (p.id, b)
                on_outline = outline.distance(Point(b)) < 0.1 and outline.distance(Point(c)) < 0.1
                assert math.dist(b, c) >= 0.5 or on_outline, (p.id, b, c)


def test_a_thin_spur_into_a_neighbour_is_removed():
    # a plane with a 0.2 ft wide, 8 ft long finger poking into the plane beside it
    left = block("left", [(0, 0), (10, 0), (10, 9.9), (18, 9.9), (18, 10.1), (10, 10.1), (10, 20), (0, 20)], aspect=270.0)
    right = block("right", [(10, 0), (20, 0), (20, 20), (10, 20)], aspect=90.0)
    planes = {p.id: p for p in snap_planes(blockset(SQ, [left, right]), clip_to_footprint=True)}
    assert planes["right"].plan_area_sqft == pytest.approx(200.0, abs=3)
    assert max(x for x, _ in planes["left"].polygon) < 10.5
