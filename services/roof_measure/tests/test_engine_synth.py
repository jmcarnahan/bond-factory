"""The engine on synthetic roofs (exact answers known): sane structure at 16 and 8 pts/m2. Bounds are loose on purpose:
the improvement builders tighten them. Synthetic data only; nothing real lives in this repo."""

import json

import pytest
from engine_cases import case, inputs, run
from shapely.ops import unary_union

from roof_measure.engine import measure_roof
from roof_measure.engine.errors import EngineTimeout

SHAPES = ("gable", "hip", "l_shape", "t_shape", "cross_gable", "flat", "flat_pitched", "two_level")
STRICT = ("gable", "hip", "flat")  # facet count within +-1 of the truth; the rest within +-2
AREA_TOL = 0.025  # phase 2b: the roof edge is measured with a spacing correction (was 0.04 at the port)
COST_KEYS = ("planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "ridge_cap_ridge_hip_ft")
GRID = [f"{s}_d{d}" for s in SHAPES for d in (16, 8)]


@pytest.mark.parametrize("name", GRID)
def test_structure_area_and_tiling(name):
    res = run(name)
    truth = case(name).roof
    shape = name.rsplit("_d", 1)[0]
    assert not res.refused and res.quality.verdict == "ok", res.quality.reasons
    assert abs(len(res.facets) - len(truth.facets)) <= (1 if shape in STRICT else 2)
    area = sum(f.area_sqft for f in res.facets)
    true_area = sum(f.area_sqft for f in truth.facets)
    assert abs(area / true_area - 1) <= AREA_TOL
    polys = [f.polygon for f in res.facets]
    union = unary_union(polys)
    overlap = sum(p.area for p in polys) - union.area
    assert overlap <= 0.001 * union.area  # zero overlap
    assert abs(union.area - res.outline.drawn.area) <= 0.001 * union.area  # tiles the roof outline
    for k in COST_KEYS:
        assert res.totals[k] is not None, k


@pytest.mark.parametrize("name", [f"{s}_d8" for s in ("gable", "flat", "flat_pitched", "two_level", "hip")])
def test_facet_types_and_edge_types(name):
    res = run(name)
    kinds = {f.roof_type for f in res.facets}
    types = {e.type for e in res.edges}
    shape = name.rsplit("_d", 1)[0]
    if shape == "flat":
        assert kinds == {"flat"} and "flat_edge" in types and not ({"ridge", "hip"} & types)
    elif shape == "gable":
        assert kinds == {"pitched"} and "ridge" in types and "eave" in types and "rake" in types
        assert all(abs(f.pitch_rise - 6.0) <= 0.7 for f in res.facets)
    elif shape == "hip":
        assert "hip" in types and "ridge" in types
    elif shape == "flat_pitched":
        assert kinds == {"flat", "pitched"} and "transition" in types
        assert res.totals["roofing_flat_sqft"] > 0 and res.totals["roofing_pitched_sqft"] > 0
    elif shape == "two_level":
        assert "step_flashing" in types  # two gables end to end, one 1.2 m higher: the step runs down the lower slope (sidewall)
        assert res.totals["lengths_ft"]["step_flashing"] > 0
        assert all(e.jump_ft is not None and e.upper for e in res.edges if e.type in ("level_change", "step_flashing", "wall_flashing"))


def test_two_runs_give_byte_identical_json():
    rp, wall, pts = inputs("l_shape_d8")
    a = measure_roof(rp, wall, outline_source="county", parcel_match="given", context=pts)
    b = measure_roof(rp, wall, outline_source="county", parcel_match="given", context=pts)
    assert json.dumps(a.to_result_json("x")) == json.dumps(b.to_result_json("x"))
    assert a.params_hash == b.params_hash and a.timings  # timings exist but are not part of the JSON
    assert "runtime_s" not in json.dumps(a.to_result_json("x"))


def test_the_result_json_has_the_harness_shape():
    out = run("hip_d8").to_result_json("hip")
    assert set(out) == {"slug", "method", "version", "roof_outline", "facets", "edges", "totals", "diagnostics"}
    f = out["facets"][0]
    assert {"id", "plane", "pitch_rise", "aspect_deg", "roof_type", "area_sqft", "polygon", "pitch_fit"} <= set(f)
    assert out["diagnostics"]["quality"]["verdict"] == "ok"
    assert out["totals"]["complexity"]["hint"] in ("simple", "cut_up")


def test_the_priced_area_is_below_the_drawn_area_and_both_are_reported():
    t = run("gable_d8").totals
    assert t["area_sqft_measured_edge"] > t["planes_surface_area_sqft"] > t["area_sqft_wall_line"] * 0.9
    # contract 0.4: area_sqft_roof_edge is the DRAWN area (it used to repeat the priced one); the priced key is
    # planes_surface_area_sqft. The engine totals may leave it to the adapter (engine.adapter.engine_totals).
    assert t.get("area_sqft_roof_edge", t["area_sqft_measured_edge"]) == t["area_sqft_measured_edge"]
    assert t["outline_perimeter_ft"] > 0 and t["outline_perimeter_wall_ft"] > 0


def test_a_rotated_roof_is_measured_in_its_own_frame():
    res = run("gable_d8_rot17")
    assert not res.refused and len(res.facets) == 2
    assert abs(res.diagnostics["frame_rot_deg"] - 17.0) <= 1.0


def test_a_thin_cloud_below_4_points_per_m2_is_refused():
    res = run("gable_d2")
    assert res.refused and res.quality.verdict == "lidar_too_sparse" and res.facets == []
    out = res.to_result_json("thin")
    assert out["facets"] == [] and out["diagnostics"]["quality"]["reasons"] == ["lidar_too_sparse"]


def test_an_expired_deadline_raises_the_typed_timeout():
    rp, wall, pts = inputs("hip_d8")
    with pytest.raises(EngineTimeout):
        measure_roof(rp, wall, deadline=0.0, outline_source="county", context=pts)


@pytest.mark.parametrize("change", [
    {"s3_axis": False}, {"s2_flat": False}, {"s4_gentle": False},
    {"overhang_scale": 1.0}, {"overhang_scale": 0.0}, {"max_points": 400}, {"beta_schedule": (3.2,)}])
def test_the_alternative_parameter_paths_still_measure_a_roof(change):
    from roof_measure.engine.params import DEFAULT

    res = run("l_shape_d8_rot17", DEFAULT.replace(**change))
    assert not res.refused and len(res.facets) >= 2
    assert res.params_hash == DEFAULT.replace(**change).stable_hash() != DEFAULT.stable_hash()


def test_the_point_cap_is_reported_in_the_diagnostics():
    from roof_measure.engine.params import DEFAULT

    res = run("l_shape_d8_rot17", DEFAULT.replace(max_points=400))
    assert res.diagnostics.get("capped") is True and res.diagnostics["n_points"] == 400
