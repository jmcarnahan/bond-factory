"""Quality metrics: plane mismatch, outline coverage, reason codes. Metrics and codes only, never a label."""

from __future__ import annotations

import pytest
from quality_helpers import SITE1, SITE1_HANDMADE, TWO_LEVEL, hip_rectangle

from roof_measure.classify import BlockSet, classify_blocks
from roof_measure.model import build_model
from roof_measure.planes import Plane, snap_with_stats
from roof_measure.quality import plane_metrics, plane_totals

KEYS = {"plane_mismatch_pct", "outline_covered_pct", "model_uncovered_pct", "level_spread_ft", "planes_lidar",
        "facets_model", "reasons"}
SQ = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]


def plane(pid="p", ring=None, pitch=4.0, aspect: float | None = 180.0, area=100.0, filled=0.0) -> Plane:
    return Plane(id=pid, polygon=ring or SQ, pitch_rise=0.0 if aspect is None else pitch, aspect_deg=aspect,
                 plan_area_sqft=area, surface_area_sqft=area, height_ft=10.0, rms_ft=0.1, filled_pct=filled)


def facet(ring=None, pitch=4.0, aspect: float | None = 180.0) -> dict:
    return {"id": "f", "kind": "flat" if aspect is None else "sloped", "polygon": ring or SQ,
            "pitch_rise": 0.0 if aspect is None else pitch, "aspect_deg": aspect}


def metrics(planes, facets, **kw):
    return plane_metrics(planes, {"facets": facets}, **kw)


def run(path_or_set):
    bs = path_or_set if isinstance(path_or_set, BlockSet) else BlockSet.load(path_or_set)
    c = classify_blocks(bs)
    model = build_model(bs, c.blocks, {"method": "lidar_skeleton"}, c)
    snap = snap_with_stats(bs, clip_to_footprint=True)
    return plane_metrics(snap.planes, model, covered_pct=snap.covered_pct), c


@pytest.mark.parametrize("path", [SITE1, SITE1_HANDMADE])
def test_real_roof_fixtures_agree_with_their_model(path):
    q, _ = run(path)
    assert q["plane_mismatch_pct"] < 15.0 and "multi_plane_simplified" not in q["reasons"]


def test_a_two_level_l_roof_squeezed_into_one_hip_is_reported():
    q, c = run(TWO_LEVEL)
    assert [r.form for r in c.blocks] == ["hip"]  # what the rules do with it
    assert q["planes_lidar"] == 8 and q["facets_model"] == 4
    assert q["plane_mismatch_pct"] >= 30.0 and "multi_plane_simplified" in q["reasons"]


def test_a_plain_hip_matches_its_planes_exactly():
    q, c = run(hip_rectangle())
    assert [r.form for r in c.blocks] == ["hip"]
    assert q["plane_mismatch_pct"] == 0.0 and q["reasons"] == [] and q["planes_lidar"] == q["facets_model"] == 4


def test_the_object_has_exactly_the_documented_keys():
    q, _ = run(hip_rectangle())
    assert set(q) == KEYS and isinstance(q["reasons"], list)


def test_aspect_tolerance_is_30_degrees():
    assert metrics([plane(aspect=180.0)], [facet(aspect=209.0)])["plane_mismatch_pct"] == 0.0
    assert metrics([plane(aspect=180.0)], [facet(aspect=211.0)])["plane_mismatch_pct"] == 100.0
    assert metrics([plane(aspect=350.0)], [facet(aspect=15.0)])["plane_mismatch_pct"] == 0.0  # wraps round north


def test_pitch_tolerance_is_one_and_a_half_in_twelve():
    assert metrics([plane(pitch=4.0)], [facet(pitch=5.4)])["plane_mismatch_pct"] == 0.0
    assert metrics([plane(pitch=4.0)], [facet(pitch=5.6)])["plane_mismatch_pct"] == 100.0


def test_a_flat_plane_must_meet_a_flat_facet():
    assert metrics([plane(aspect=None)], [facet(aspect=None)])["plane_mismatch_pct"] == 0.0
    assert metrics([plane(aspect=None)], [facet(pitch=0.5, aspect=180.0)])["plane_mismatch_pct"] == 100.0
    assert metrics([plane(aspect=180.0)], [facet(aspect=None)])["plane_mismatch_pct"] == 100.0


def test_the_best_overlap_facet_is_the_one_compared():
    left, right = [[0, 0], [6, 0], [6, 10], [0, 10]], [[6, 0], [10, 0], [10, 10], [6, 10]]
    facets = [facet(left, aspect=0.0), facet(right, aspect=180.0)]  # the plane overlaps `left` more
    assert metrics([plane(aspect=180.0)], facets)["plane_mismatch_pct"] == 100.0
    assert metrics([plane(aspect=0.0)], facets)["plane_mismatch_pct"] == 0.0


def test_a_plane_with_no_facet_under_it_is_a_mismatch_and_the_share_is_area_weighted():
    far = [[100, 100], [110, 100], [110, 110], [100, 110]]
    m = metrics([plane("a", area=300.0), plane("b", far, area=100.0)], [facet()])
    assert m["plane_mismatch_pct"] == 25.0  # b (100 of 400 sq ft) has no facet


def test_no_planes_means_no_numbers_and_no_reasons():
    m = metrics([], [facet()])
    assert m == {"plane_mismatch_pct": None, "outline_covered_pct": None, "model_uncovered_pct": None,
                 "level_spread_ft": None, "planes_lidar": 0, "facets_model": 1,
                 "reasons": []}


def test_multi_plane_simplified_needs_three_more_planes_and_30_percent():
    bad = [plane(f"p{i}", aspect=0.0) for i in range(4)]  # every plane disagrees with the one south facet
    assert "multi_plane_simplified" in metrics(bad, [facet()])["reasons"]  # 4 planes >= 1 facet + 3
    assert "multi_plane_simplified" not in metrics(bad[:3], [facet()])["reasons"]  # 3 < 1 + 3
    good = [plane(f"p{i}", aspect=180.0) for i in range(4)]
    assert "multi_plane_simplified" not in metrics(good, [facet()])["reasons"]  # mismatch 0
    mixed = [plane("a", area=100.0, aspect=0.0)] + [plane(f"g{i}", area=100.0) for i in range(3)]
    assert metrics(mixed, [facet()])["plane_mismatch_pct"] == 25.0
    assert "multi_plane_simplified" not in metrics(mixed, [facet()])["reasons"]  # 25 < 30


def test_low_outline_coverage_below_70_percent():
    p = [plane()]
    assert "low_outline_coverage" in metrics(p, [facet()], covered_pct=69.9)["reasons"]
    assert "low_outline_coverage" not in metrics(p, [facet()], covered_pct=70.0)["reasons"]
    assert metrics(p, [facet()], covered_pct=69.94)["outline_covered_pct"] == 69.9


def test_coverage_defaults_to_what_the_planes_did_not_fill():
    m = metrics([plane("a", area=300.0, filled=0.0), plane("b", area=100.0, filled=100.0)], [facet()])
    assert m["outline_covered_pct"] == 75.0


def test_warning_codes_become_reasons_in_a_fixed_order():
    codes = ["other_buildings_on_parcel", "parcel_street_match", "low_point_density", "verifier_unverified"]
    m = metrics([plane()], [facet()], warning_codes=codes, covered_pct=50.0)
    assert m["reasons"] == ["low_outline_coverage", "sparse_lidar", "parcel_street_match", "other_buildings_on_parcel"]
    assert metrics([plane()], [facet()], warning_codes=["verifier_unverified"])["reasons"] == []


def test_agent_failed_fell_back_passes_through_as_a_reason():
    m = metrics([plane()], [facet()], warning_codes=["agent_failed_fell_back", "agent_retry_used"])
    assert m["reasons"] == ["agent_failed_fell_back"]  # agent_retry_used is not a code this module reports


def test_values_are_rounded_to_one_decimal():
    m = metrics([plane("a", area=100.0, aspect=0.0), plane("b", area=200.0)], [facet()], covered_pct=81.2345)
    assert m["plane_mismatch_pct"] == 33.3 and m["outline_covered_pct"] == 81.2


def test_plane_totals_are_area_weighted_and_rounded():
    t = plane_totals([plane("a", pitch=3.0, area=100.0), plane("b", [[0, 0], [20, 0], [20, 10], [0, 10]], pitch=6.0, area=200.0)])
    assert set(t) == {"planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "plane_count"}
    assert t["planes_surface_area_sqft"] == 300.0 and t["planes_pitch_weighted"] == 5.0 and t["plane_count"] == 2
    assert t["outline_perimeter_ft"] == 60.0  # the two squares overlap, so the union is the 20 x 10 rectangle


def test_a_sloped_plane_without_an_aspect_is_flat():
    assert metrics([plane(aspect=None, pitch=4.0)], [facet(aspect=None)])["plane_mismatch_pct"] == 0.0
    p = Plane(id="p", polygon=SQ, pitch_rise=4.0, aspect_deg=None, plan_area_sqft=100.0, surface_area_sqft=100.0,
              height_ft=1.0, rms_ft=0.0, filled_pct=0.0)
    assert metrics([p], [facet(pitch=4.0, aspect=180.0)])["plane_mismatch_pct"] == 100.0  # not a sloped match


def test_a_plane_or_facet_under_half_in_twelve_is_flat():
    assert metrics([plane(pitch=0.3, aspect=90.0)], [facet(aspect=None)])["plane_mismatch_pct"] == 0.0
    assert metrics([plane(aspect=None)], [facet(pitch=0.3, aspect=90.0)])["plane_mismatch_pct"] == 0.0
    assert metrics([plane(pitch=0.3, aspect=90.0)], [facet(pitch=0.4, aspect=270.0)])["plane_mismatch_pct"] == 0.0
    assert metrics([plane(pitch=0.6, aspect=90.0)], [facet(aspect=None)])["plane_mismatch_pct"] == 100.0
    assert metrics([plane(aspect=None)], [facet(pitch=0.6, aspect=180.0)])["plane_mismatch_pct"] == 100.0


def test_failed_assessment_says_quality_failed_and_keeps_the_codes_it_knows():
    from roof_measure.quality import failed_assessment

    q = failed_assessment({"facets": [1, 2]}, ["parcel_street_match", "low_point_density"], planes_lidar=7)["quality"]
    assert q == {"plane_mismatch_pct": None, "outline_covered_pct": None, "model_uncovered_pct": None,
                 "level_spread_ft": None, "planes_lidar": 7, "facets_model": 2,
                 "reasons": ["quality_failed", "parcel_street_match"]}


def test_model_uncovered_is_the_plane_area_outside_the_model():
    right = [[10, 0], [20, 0], [20, 10], [10, 10]]
    two = [plane("a", SQ, area=100.0), plane("b", right, area=100.0)]
    assert metrics(two, [facet(SQ)])["model_uncovered_pct"] == 50.0  # b lies wholly outside the model's facets
    assert metrics(two, [facet(SQ), facet(right)])["model_uncovered_pct"] == 0.0
    assert metrics(two, [])["model_uncovered_pct"] == 100.0
    assert metrics([], [facet()])["model_uncovered_pct"] is None
    half = [[0, 0], [5, 0], [5, 10], [0, 10]]
    assert metrics([plane("a", SQ, area=100.0)], [facet(half)])["model_uncovered_pct"] == 50.0


def test_model_misses_roof_area_fires_at_ten_percent():
    nine = [[0, 0], [10, 0], [10, 9.1], [0, 9.1]]  # 91 of 100 sq ft covered: 9% missing
    eleven = [[0, 0], [10, 0], [10, 8.9], [0, 8.9]]
    assert "model_misses_roof_area" not in metrics([plane()], [facet(nine)])["reasons"]
    assert "model_misses_roof_area" in metrics([plane()], [facet(eleven)])["reasons"]


def test_level_spread_uses_planes_with_at_least_five_percent_of_the_area():
    def at(pid, h, area):
        p = plane(pid, area=area)
        p.height_ft = h
        return p

    m = metrics([at("a", 16.0, 600.0), at("b", 11.0, 300.0), at("tiny", 30.0, 20.0)], [facet()])
    assert m["level_spread_ft"] == 5.0  # the 20 sq ft plane (2%) does not count
    assert metrics([at("a", 12.0, 100.0)], [facet()])["level_spread_ft"] == 0.0
