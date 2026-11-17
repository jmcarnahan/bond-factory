"""Sliver cleanup: a thin spike goes, a legitimate narrow facet stays, totals and validate stay consistent."""

import copy
import json
import math

import pytest
import spike_cases
from conftest import FIXTURES

from roof_measure import model as model_mod
from roof_measure import model_cleanup as model_cleanup_mod
from roof_measure.model import ModelError, _totals, validate
from roof_measure.model_cleanup import clean_facets, interior_angle

HERE_FIXTURES = spike_cases.FIXTURES
FLAT = json.loads((FIXTURES / "synthetic_flat_parapet.json").read_text())


def with_spike(half_base: float, height: float):
    """The 60 x 40 flat roof with a triangular spike on its north side (tip angle set by base and height)."""
    m = copy.deepcopy(FLAT)
    tip = [30.0, 40.0 + height]
    left, right = [30.0 - half_base, 40.0], [30.0 + half_base, 40.0]
    f = m["facets"][0]
    f["polygon"] = [[0.0, 0.0], [60.0, 0.0], [60.0, 40.0], right, tip, left, [0.0, 40.0]]
    f["plan_area_sqft"] = f["area_sqft"] = 2400.0 + half_base * height
    m["blocks"][0]["plan_area_sqft"] = 2400.0
    m["edges"] = [e for e in m["edges"] if e["id"] != "e3"] + [
        {"id": "e3", "type": "parapet", "points": [[60.0, 40.0], right], "length_ft": 30.0 - half_base, "facets": ["f1"]},
        {"id": "e5", "type": "parapet", "points": [right, tip], "length_ft": math.dist(right, tip), "facets": ["f1"]},
        {"id": "e6", "type": "parapet", "points": [tip, left], "length_ft": math.dist(tip, left), "facets": ["f1"]},
        {"id": "e7", "type": "parapet", "points": [left, [0.0, 40.0]], "length_ft": 30.0 - half_base, "facets": ["f1"]}]
    m["totals"] = _totals(m["facets"], m["edges"])
    return m, tip


def test_the_angle_helper():
    assert interior_angle((1, 0), (0, 0), (0, 1)) == pytest.approx(90)
    assert interior_angle((1, 0), (0, 0), (1, 0.0001)) < 1
    assert interior_angle((0, 0), (0, 0), (1, 1)) == 180


def test_a_six_degree_spike_fails_validate_and_passes_after_cleanup():
    m, tip = with_spike(0.35, 6.7)  # tip angle about 6 degrees, spike area about 0.1% of the facet
    assert interior_angle([30.35, 40.0], tip, [29.65, 40.0]) < 8
    with pytest.raises(ModelError, match="spike"):
        validate(m)
    notes = clean_facets(m["facets"], m["edges"])
    assert notes == ["facet f1: sliver vertex removed"]
    m["totals"] = _totals(m["facets"], m["edges"])
    validate(m)
    assert [p for p in m["facets"][0]["polygon"] if p == list(tip)] == []
    assert m["facets"][0]["plan_area_sqft"] == pytest.approx(2400.0, abs=0.01)  # the spike's area is gone
    assert not {"e5", "e6"} & {e["id"] for e in m["edges"]}  # edges that only bounded the spike are dropped
    assert m["totals"]["lengths_ft"]["parapet"] == pytest.approx(sum(e["length_ft"] for e in m["edges"]))


def test_a_shared_edge_keeps_its_other_facet():
    m, _ = with_spike(0.35, 6.7)
    for e in m["edges"]:
        if e["id"] == "e5":
            e["facets"] = ["f1", "f9"]
    clean_facets(m["facets"], m["edges"])
    e5 = next(e for e in m["edges"] if e["id"] == "e5")
    assert e5["facets"] == ["f9"]


def test_a_legitimate_narrow_facet_is_untouched():
    m, _ = with_spike(1.2, 6.7)  # tip angle about 20 degrees
    before = copy.deepcopy(m)
    assert clean_facets(m["facets"], m["edges"]) == []
    assert m == before
    validate(m)


def test_a_spike_that_costs_too_much_area_is_left_for_validate_to_reject():
    m, _ = with_spike(2.0, 40.0)  # tip about 5.7 degrees, 80 sq ft = 3% of the facet
    before = copy.deepcopy(m["facets"])
    assert clean_facets(m["facets"], m["edges"]) == [] and m["facets"] == before


def test_near_duplicate_vertices_are_merged_and_edges_snapped():
    m = copy.deepcopy(FLAT)
    m["facets"][0]["polygon"] = [[0.0, 0.0], [60.0, 0.0], [60.0, 0.02], [60.0, 40.0], [0.0, 40.0]]
    m["edges"][1]["points"] = [[60.0, 0.02], [60.0, 40.0]]
    clean_facets(m["facets"], m["edges"])
    assert m["facets"][0]["polygon"] == [[0.0, 0.0], [60.0, 0.0], [60.0, 40.0], [0.0, 40.0]]
    assert m["edges"][1]["points"] == [[60.0, 0.0], [60.0, 40.0]]
    m["totals"] = _totals(m["facets"], m["edges"])
    validate(m)


def test_clean_models_are_left_alone():
    for name in ("synthetic_hip", "synthetic_gable", "synthetic_flat_parapet", "synthetic_hip_zigzag", "site1_lidar"):
        m = json.loads((FIXTURES / f"{name}.json").read_text())
        before = copy.deepcopy(m)
        assert clean_facets(m["facets"], m["edges"]) == [] and m == before, name


def test_build_model_runs_the_cleanup_and_reports_its_notes(monkeypatch):
    from roof_measure.synth import synthetic_hip

    monkeypatch.setattr(model_mod, "clean_facets", lambda facets, edges: ["facet f1: sliver vertex removed"])
    bs, rbs = synthetic_hip()
    m = model_mod.build_model(bs, rbs, {"method": "fixture"})
    assert "facet f1: sliver vertex removed" in m["warnings"]


def test_dedupe_terminates_on_exact_duplicates_first_equals_last_and_chains():
    from roof_measure.model_cleanup import _dedupe

    ring, moved = _dedupe([(0, 0), (10, 0), (10, 0), (10, 10)])
    assert ring == [(0, 0), (10, 0), (10, 10)] and moved == {}
    ring, moved = _dedupe([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])  # first == last
    assert ring == [(0, 0), (10, 0), (10, 10), (0, 10)] and moved == {}
    ring, moved = _dedupe([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.02), (0.0, 0.04)])  # a -> b -> c
    assert ring == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert moved == {(0.0, 0.02): (0.0, 0.0), (0.0, 0.04): (0.0, 0.0)}
    ring, moved = _dedupe([(1, 1), (1, 1), (1, 1)])
    assert ring == [(1, 1)] and moved == {}


def test_clean_facets_removes_exact_duplicate_vertices_and_build_model_finishes_fast(monkeypatch):
    import time

    from roof_measure.synth import synthetic_hip

    f = {"id": "f1", "polygon": [[0, 0], [10, 0], [10, 0], [10, 10], [0, 10], [0, 0]], "pitch_rise": 0.0,
         "plan_area_sqft": 100.0, "area_sqft": 100.0}
    start = time.monotonic()
    clean_facets([f], [])
    assert time.monotonic() - start < 1.0 and f["polygon"] == [[0, 0], [10, 0], [10, 10], [0, 10]]
    bs, rbs = synthetic_hip()
    bs.footprint_ft = [bs.footprint_ft[0], bs.footprint_ft[0], *bs.footprint_ft[1:]]  # a duplicated footprint vertex
    rbs[0].polygon = [rbs[0].polygon[0], rbs[0].polygon[0], *rbs[0].polygon[1:]]
    start = time.monotonic()
    try:
        m = model_mod.build_model(bs, rbs, {"method": "fixture"})
    except ModelError:
        m = None  # rejecting a degenerate ring is acceptable; hanging is not
    assert time.monotonic() - start < 1.0
    assert m is None or m["totals"]["total_area_sqft"] == pytest.approx(959.2, abs=1.0)


# ---- sliver facets: a spike facet that is tiny is merged into its same-block neighbour (model_slivers.py)
def two_facets(with_right_neighbour=True):
    """A 60 x 40 facet f1, its thin triangle f2 (tip angle 5.7 degrees on the outline, 20 sq ft) and, when asked, the
    facet f3 on the other side of the triangle's long side: only the union with f3 loses the sharp tip."""
    pitch = {"pitch_rise": 4.0, "kind": "sloped", "block": "b1"}
    big = {"id": "f1", "polygon": [[0.0, 0.0], [60.0, 0.0], [60.0, 40.0], [0.0, 40.0]], "aspect_deg": 180.0,
           "plan_area_sqft": 2400.0, "area_sqft": 2400.0 * math.sqrt(1 + 1 / 9), **pitch}
    thin = {"id": "f2", "polygon": [[60.0, 0.0], [80.0, 0.0], [60.0, 2.0]], "aspect_deg": 90.0,
            "plan_area_sqft": 20.0, "area_sqft": 20.0 * math.sqrt(1 + 1 / 9), **pitch}
    right = {"id": "f3", "polygon": [[60.0, 2.0], [80.0, 0.0], [100.0, 0.0], [100.0, 40.0], [60.0, 40.0]],
             "aspect_deg": 0.0, "plan_area_sqft": 1580.0, "area_sqft": 1580.0 * math.sqrt(1 + 1 / 9), **pitch}
    edges = [{"id": "e1", "type": "eave", "points": [[0.0, 0.0], [60.0, 0.0]], "length_ft": 60.0, "facets": ["f1"]},
             {"id": "e2", "type": "eave", "points": [[60.0, 0.0], [80.0, 0.0]], "length_ft": 20.0, "facets": ["f2"]},
             {"id": "e3", "type": "hip", "points": [[80.0, 0.0], [60.0, 2.0]], "length_ft": 20.1, "facets": ["f2", "f3"]},
             {"id": "e4", "type": "ridge", "points": [[60.0, 0.0], [60.0, 2.0]], "length_ft": 2.0, "facets": ["f1", "f2"]}]
    return ([big, thin, right] if with_right_neighbour else [big, thin]), edges


def test_a_sliver_facet_is_merged_into_the_neighbour_that_removes_its_spike():
    facets, edges = two_facets()
    surface = {f["id"]: f["area_sqft"] for f in facets}
    notes = clean_facets(facets, edges)
    assert notes == ["facet f2: sliver merged into facet f3"]  # f1 shares 2 ft but would keep the 5.7 degree tip
    assert [f["id"] for f in facets] == ["f1", "f3"]
    f3 = facets[1]
    assert sorted(map(tuple, f3["polygon"])) == [(60.0, 0.0), (60.0, 40.0), (100.0, 0.0), (100.0, 40.0)]  # a rectangle
    assert f3["plan_area_sqft"] == pytest.approx(1600.0)
    assert f3["area_sqft"] == pytest.approx(surface["f2"] + surface["f3"])  # nothing lost, same pitch
    assert {e["id"]: e["facets"] for e in edges} == {"e1": ["f1"], "e2": ["f3"], "e4": ["f1", "f3"]}  # e3 was the border
    assert all(interior_angle(f["polygon"][i - 1], f["polygon"][i], f["polygon"][(i + 1) % len(f["polygon"])]) >= 10
               for f in facets for i in range(len(f["polygon"])))


def test_a_sliver_whose_only_neighbour_keeps_its_tip_is_left_alone():
    facets, edges = two_facets(with_right_neighbour=False)
    before = copy.deepcopy((facets, edges))
    assert clean_facets(facets, edges) == []
    assert (facets, edges) == before


def test_a_sliver_over_the_area_bound_is_left_alone():
    facets, edges = two_facets()
    facets[1]["polygon"] = [[60.0, 0.0], [120.0, 0.0], [60.0, 8.0]]  # 240 sq ft, tip 7.6 degrees, over 25 sq ft
    before = copy.deepcopy((facets, edges))
    assert clean_facets(facets, edges) == []
    assert (facets, edges) == before


def test_a_sliver_with_no_neighbour_in_its_block_is_left_alone():
    facets, edges = two_facets()
    facets[1]["block"] = "b2"  # f1 and f3 belong to b1
    before = copy.deepcopy((facets, edges))
    assert clean_facets(facets, edges) == []
    assert (facets, edges) == before


def test_a_small_facet_without_a_spike_is_never_merged():
    facets, edges = two_facets()
    facets[1]["polygon"] = [[60.0, 0.0], [66.0, 0.0], [60.0, 6.0]]  # 18 sq ft, 45 degree tip
    before = copy.deepcopy((facets, edges))
    assert clean_facets(facets, edges) == []
    assert (facets, edges) == before


@pytest.mark.parametrize("name", spike_cases.FIXABLE)
def test_a_jagged_roof_with_a_spike_facet_now_builds_with_the_area_unchanged(name):
    with pytest.raises(ModelError, match="spike"):  # the 0.3.0 behaviour: no merge, the model is rejected
        original = model_cleanup_mod.merge_slivers
        model_cleanup_mod.merge_slivers = lambda facets, edges: []
        try:
            spike_cases.build(name)
        finally:
            model_cleanup_mod.merge_slivers = original
    m = spike_cases.build(name)
    rb = spike_cases.roof_block(name)
    expected = rb.poly.area * math.sqrt(1 + (rb.pitch_rise / 12) ** 2)
    assert m["totals"]["total_area_sqft"] == pytest.approx(expected, rel=0.01)
    assert any("sliver merged into" in w for w in m["warnings"])
    assert all(len(set(e["facets"])) == len(e["facets"]) for e in m["edges"])  # no edge lists a facet twice


def test_a_spike_that_is_no_sliver_is_still_rejected():
    with pytest.raises(ModelError, match="spike"):
        spike_cases.build(spike_cases.UNFIXABLE)


def test_merging_slivers_changes_nothing_on_every_committed_blocks_fixture(tmp_path):
    """The guard: only a model that would fail validate is touched, so every roof that works today is identical."""
    from quality_helpers import ROOT, SITE1, TWO_LEVEL

    from roof_measure.classify import BlockSet, classify_blocks

    files = [SITE1, TWO_LEVEL, *(HERE_FIXTURES.glob("*_blocks.json")), ROOT / "fixtures" / "site1_blocks.json"]
    assert len(files) >= 5
    for f in files:
        bs = BlockSet.load(f)
        cl = classify_blocks(bs)
        with_merge = model_mod.build_model(bs, cl.blocks, {"method": "lidar_skeleton"}, cl)
        original = model_cleanup_mod.merge_slivers
        model_cleanup_mod.merge_slivers = lambda facets, edges: []
        try:
            without = model_mod.build_model(bs, cl.blocks, {"method": "lidar_skeleton"}, cl)
        finally:
            model_cleanup_mod.merge_slivers = original
        for m in (with_merge, without):
            m.pop("generated_at")
        assert with_merge == without, f.name
