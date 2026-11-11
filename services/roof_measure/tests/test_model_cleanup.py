"""Sliver cleanup: a thin spike goes, a legitimate narrow facet stays, totals and validate stay consistent."""

import copy
import json
import math

import pytest
from conftest import FIXTURES

from roof_measure import model as model_mod
from roof_measure.model import ModelError, _totals, validate
from roof_measure.model_cleanup import clean_facets, interior_angle

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
