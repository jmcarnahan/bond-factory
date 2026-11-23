"""The adapter: engine result -> validated roof model (bond.roof_model/0.1 + contract 0.4) and the envelope's totals,
quality and planes, on the synthetic roofs (the only roofs in this repo)."""

from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest
from engine_cases import _cases, case, run
from shapely.geometry import Polygon

from roof_measure.classify import BlockSet
from roof_measure.engine import adapter, synth_points
from roof_measure.engine.load import roof_points_from_arrays
from roof_measure.envelope import WARNING_CODES, build_envelope
from roof_measure.model import CORE_EDGE_TYPES, EDGE_TYPES, ModelError, _totals, validate
from roof_measure.quality import assess_engine

FT = 1 / 0.3048
SHAPES = [n for n in _cases() if n.endswith("_d8")]
KNOWN_GEOMETRY_LIMIT = {
    "complex_hip_d8": "a 20-facet roof: the partition (not the adapter) misses valley and hip length",
    "dutch_gable_d8": "the partition leaves a 4 ft sliver of rake beside the small gable (engine geometry, not typing)"}


def base() -> BlockSet:
    return BlockSet(address={"formatted": "1 Example St"}, origin={"lat": 0.0, "lng": 0.0}, frame={}, footprint_ft=[],
                    footprint_meta={"provider": "lacounty_lariac_2020", "id": "T1", "area_sqft": 1000.0},
                    lidar={"project": "synthetic", "acquired": None, "points_on_roof": 5000, "density_per_m2": 8.0})


def model_of(name: str) -> tuple[dict, object]:
    res = run(name)
    return adapter.engine_model(res, base(), 0.0), res


def finite(v) -> bool:
    if isinstance(v, dict):
        return all(finite(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return all(finite(x) for x in v)
    return not isinstance(v, float) or math.isfinite(v)


@pytest.mark.parametrize("name", SHAPES)
def test_every_shape_becomes_a_valid_model_with_finite_totals(name):
    model, res = model_of(name)
    validate(model)  # engine_model validated it; again, as a reader would
    assert model["schema"] == "bond.roof_model/0.1" and model["units"] == "ft" and model["source"]["engine"] == "planes/1"
    assert len(model["facets"]) == len(model["blocks"]) == len(res.facets) and finite(model)
    assert set(model["totals"]["lengths_ft"]) == set(EDGE_TYPES)  # an engine model carries all twelve keys
    for f in model["facets"]:
        assert {"roof_type", "pitch_fit", "pitch_sigma", "borderline", "supported_pct", "points", "rms_ft", "plane_eq"} <= set(f)
        assert (f["kind"] == "flat") == (f["pitch_rise"] < 0.5) and (f["aspect_deg"] is None) == (f["kind"] == "flat")
    t = adapter.engine_totals(res)
    assert finite(t)
    json.dumps({"model": model, "totals": t}, allow_nan=False)


@pytest.mark.parametrize("name", SHAPES)
def test_the_cost_sheet_keys_are_present_priced_and_consistent(name):
    model, res = model_of(name)
    t = adapter.engine_totals(res)
    for k in ("planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "ridge_cap_ridge_hip_ft"):
        assert isinstance(t[k], (int, float)) and math.isfinite(t[k]), k
    drawn = model["totals"]["total_area_sqft"]
    assert t["area_sqft_roof_edge"] == pytest.approx(drawn, abs=0.2)  # the drawn (measured roof edge) area
    assert t["area_sqft_wall_line"] - 0.5 <= t["planes_surface_area_sqft"] <= t["area_sqft_roof_edge"] + 0.5  # priced between
    assert t["roofing_pitched_sqft"] + t["roofing_flat_sqft"] == pytest.approx(t["planes_surface_area_sqft"], abs=0.2)
    assert t["roofing_pitched_squares"] + t["roofing_flat_squares"] == pytest.approx(t["planes_surface_area_sqft"] / 100, abs=0.03)
    lengths = model["totals"]["lengths_ft"]
    assert t["flat_edge_ft"] == pytest.approx(lengths["flat_edge"], rel=0.05, abs=2.0)
    if name not in KNOWN_GEOMETRY_LIMIT:  # the priced clip trims what the partition got wrong on those two
        assert t["level_change_ft"] == pytest.approx(lengths["level_change"], rel=0.05, abs=2.0)
    assert t["ridge_cap_ridge_hip_ft"] == pytest.approx(lengths["ridge"] + lengths["hip"], rel=0.08, abs=2.0)
    perimeter = lengths["eave"] + lengths["rake"] + lengths["flat_edge"]
    assert t["outline_perimeter_ft"] <= perimeter + 0.5 and t["outline_perimeter_ft"] >= 0.85 * perimeter  # priced edge
    assert set(t["complexity"]) == {"facets", "hip_valley_ft_per_square", "hint"} and t["complexity"]["hint"] in ("simple", "cut_up")
    assert t["plane_count"] == len(model["facets"])
    if t["roofing_pitched_sqft"]:
        assert 2.0 <= t["planes_pitch_weighted"] <= 12.0
    # the engine's own kept keys keep their 0.5/12 meaning: pitched_area + flat_area = total in the MODEL totals
    mt = model["totals"]
    assert mt["pitched_area_sqft"] + mt["flat_area_sqft"] == pytest.approx(mt["total_area_sqft"], abs=0.5)


@pytest.mark.parametrize("name", [n for n in SHAPES if "flat" in n or n in ("gable_d8", "hip_d8", "two_level_d8")])
def test_flat_and_pitched_split_matches_the_exact_roof(name):
    model, _res = model_of(name)
    c = case(name)
    flat = sum(f["area_sqft"] for f in model["facets"] if f["roof_type"] == "flat")
    pitched = sum(f["area_sqft"] for f in model["facets"] if f["roof_type"] == "pitched")
    total = flat + pitched
    assert abs(flat - c.roof.totals["flat_sqft"]) <= 0.03 * total
    assert abs(pitched - c.roof.totals["pitched_sqft"]) <= 0.03 * total


def _lengths(edges) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in edges:
        out[e["type"]] = out.get(e["type"], 0.0) + e["length_ft"]
    return out


@pytest.mark.parametrize("name", [pytest.param(n, marks=pytest.mark.xfail(reason=KNOWN_GEOMETRY_LIMIT[n], strict=True))
                                  if n in KNOWN_GEOMETRY_LIMIT else n for n in SHAPES])
def test_edge_lengths_are_within_5_percent_of_exact_and_jumps_within_015_m(name):
    model, _res = model_of(name)
    c = case(name)
    got = _lengths(model["edges"])
    want: dict[str, float] = {}
    for e in c.roof.edges:
        want[e.type] = want.get(e.type, 0.0) + e.length_ft
    for t in ("eave", "rake", "ridge", "hip", "valley", "flat_edge", "level_change", "transition"):
        a, b = got.get(t, 0.0), want.get(t, 0.0)
        assert abs(a - b) <= max(0.05 * b, 1.0), (t, a, b)
    exact = [e for e in c.roof.edges if e.type == "level_change"]
    mine = [e for e in model["edges"] if e["type"] == "level_change"]
    for e in mine:
        mid = ((e["points"][0][0] + e["points"][1][0]) / 2, (e["points"][0][1] + e["points"][1][1]) / 2)
        near = min(exact, key=lambda x: math.dist(mid, ((x.p0[0] + x.p1[0]) / 2 * FT, (x.p0[1] + x.p1[1]) / 2 * FT)))
        assert abs(e["jump_ft"] - near.jump_ft) <= 0.15 * FT, (e["jump_ft"], near.jump_ft)


def test_a_shed_high_side_is_a_rake_flagged_high_edge_in_the_model():
    model, _ = model_of("shed_d8")
    assert "ridge" not in _lengths(model["edges"])
    assert sum(1 for e in model["edges"] if e.get("high_edge")) == 1


def test_a_level_change_edge_carries_its_jump_and_only_that_type_does():
    model, _ = model_of("two_level_d8")
    lc = [e for e in model["edges"] if e["type"] == "level_change"]
    assert lc and all(e["jump_ft"] > 0.3 * FT for e in lc)
    assert not any("jump_ft" in e for e in model["edges"] if e["type"] != "level_change")


def test_the_model_planes_and_the_height_datum_are_feet_above_ground():
    res = run("gable_d8")
    ground = 120.0
    shifted = replace(res, facets=[replace(f, plane=(f.plane[0], f.plane[1], f.plane[2] + ground)) for f in res.facets],
                      edges=[replace(e, p0=(e.p0[0], e.p0[1], e.p0[2] + ground), p1=(e.p1[0], e.p1[1], e.p1[2] + ground))
                             for e in res.edges])
    model = adapter.engine_model(shifted, base(), ground)
    plain = adapter.engine_model(res, base(), 0.0)
    for a, b in zip(model["facets"], plain["facets"], strict=True):
        assert a["plane_eq"] == pytest.approx(b["plane_eq"], abs=1e-3)
        assert a["pitch_rise"] == pytest.approx(b["pitch_rise"])
    heights = [bl["eave_height_ft"] for bl in model["blocks"]]
    assert all(2.0 < h < 25.0 for h in heights)  # a 3 m eave is about 10 ft, not 120 m above sea level
    planes = adapter.engine_planes(model)
    assert len(planes) == len(model["facets"]) and all(p["plane_eq"] == f["plane_eq"] for p, f in zip(planes, model["facets"], strict=True))


def test_a_refused_result_and_an_empty_one_are_a_model_error_not_a_crash():
    refused = roof_points_from_arrays(__import__("numpy").zeros((0, 3)), Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]))
    from roof_measure.engine import measure_roof

    res = measure_roof(refused, Polygon([(0, 0), (10, 0), (10, 8), (0, 8)]))
    assert res.refused
    with pytest.raises(ModelError):
        adapter.engine_model(res, base(), 0.0)


def test_a_sharp_corner_is_removed_so_the_model_validates():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (5.0, 5.2), (0.0, 5.0)]
    needle = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (5.05, 10.0), (5.0, 0.2), (4.95, 10.0), (0.0, 10.0)]
    assert adapter.despike(ring) == ring
    out = adapter.despike(needle)
    assert (5.0, 0.2) not in out and len(out) == len(needle) - 1
    assert min(adapter._corner_deg(out[i - 1], out[i], out[(i + 1) % len(out)]) for i in range(len(out))) >= 10.0


def test_the_engine_quality_and_assessment_for_the_envelope():
    model, res = model_of("l_shape_d8")
    a = assess_engine(res, model, ["parcel_street_match"])
    q = a["quality"]
    assert q["engine"] == "planes/1" and q["verdict"] == "ok" and q["overhang_scale"] == 0.5
    for k in ("fit_covered", "fit_all", "coverage", "supported_pct", "density_pts_m2", "parcel_match", "outline_source"):
        assert k in q
    for k in ("plane_mismatch_pct", "outline_covered_pct", "model_uncovered_pct", "level_spread_ft", "planes_lidar", "facets_model"):
        assert k in q  # the 0.3 keys, with engine analogues
    assert q["facets_model"] == len(model["facets"]) and "parcel_street_match" in q["reasons"]
    assert len(a["planes"]) == len(model["facets"]) and a["totals"]["planes_surface_area_sqft"] > 0


def test_the_envelope_carries_everything_and_serialises():
    model, res = model_of("flat_pitched_step_d8")
    assessment = assess_engine(res, model, [])
    verification = {"verdict": "unverified", "notes": [], "adjustments": [], "original_totals": {}, "model": None, "rounds": 0,
                    "usage": {"input_tokens": 0, "output_tokens": 0}}
    env = build_envelope(model, method_used="lidar_skeleton", footprint_source="lariac", verification=verification,
                         warnings=["Low slope."], warning_codes=["low_slope_confirm"], density_pts_m2=8.0, assessment=assessment)
    json.dumps(env, allow_nan=False)
    t = env["totals"]
    for k in ("area_sqft", "squares", "planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft",
              "ridge_cap_ridge_hip_ft", "area_sqft_roof_edge", "area_sqft_wall_line", "roofing_flat_sqft", "complexity"):
        assert k in t, k
    assert t["planes_surface_area_sqft"] == t["area_sqft"] < t["area_sqft_roof_edge"]  # priced (overhang scale 0.5), drawn above
    assert env["warning_codes"] == ["low_slope_confirm"] and env["model"]["quality"]["engine"] == "planes/1"
    assert env["model"]["planes"] and env["model"]["totals"]["lengths_ft"]["level_change"] > 0
    for code in ("low_slope_confirm", "outline_mismatch", "poor_fit", "low_density"):
        assert code in WARNING_CODES


def test_a_borderline_low_slope_roof_is_flagged_for_confirmation():
    """A 2/12 gable straddles the flat cut: a facet is flagged, its area is reported, the reason is raised. (The
    fixed seed is chosen so the flag shows: 2.0/12 measures 2.01 and 1.97 with a sigma of 0.01 each.)"""
    roof = synth_points.gable(pitch=2.0)
    pts = synth_points.simulate(roof, density=8, seed=3)
    wall = roof.wall_polygon()
    from roof_measure.engine import measure_roof

    res = measure_roof(roof_points_from_arrays(pts[pts[:, 3] == 1][:, :3], wall, pts), wall, outline_source="county", context=pts)
    assert not res.refused
    flagged = [f for f in res.facets if f.borderline]
    drawn = sum(f.area_sqft for f in flagged)  # the total is priced (clipped to the priced roof edge): a little less
    assert flagged and 0.8 * drawn <= res.totals["low_slope_confirm_sqft"] <= drawn + 0.5
    model = adapter.engine_model(res, base(), 0.0)
    assert any(f["borderline"] for f in model["facets"])
    q = assess_engine(res, model, [])["quality"]
    assert "low_slope_confirm" in q["reasons"]
    assert adapter.engine_totals(res)["low_slope_confirm_sqft"] > 0


# ----------------------------------------------------------------------------- model.py: the two new edge types
def test_the_block_path_keeps_its_ten_length_keys_and_the_new_types_only_appear_when_used():
    facets = [{"area_sqft": 100.0, "kind": "flat", "pitch_rise": 0.0}]
    ten = _totals(facets, [{"type": "eave", "length_ft": 10.0}])
    assert set(ten["lengths_ft"]) == set(CORE_EDGE_TYPES)
    assert set(_totals(facets, [{"type": "eave", "length_ft": 10.0}], engine=True)["lengths_ft"]) == set(EDGE_TYPES)
    with_new = _totals(facets, [{"type": "flat_edge", "length_ft": 10.0}])
    assert with_new["lengths_ft"]["flat_edge"] == 10.0 and "level_change" in with_new["lengths_ft"]
    assert EDGE_TYPES[:10] == CORE_EDGE_TYPES and EDGE_TYPES[10:] == ("flat_edge", "level_change")


def test_models_stored_before_the_engine_still_validate_and_a_stray_key_does_not():
    model, _ = model_of("gable_d8")
    old = json.loads(json.dumps(model))
    for k in ("flat_edge", "level_change"):
        del old["totals"]["lengths_ft"][k]  # a result stored before 0.5.0 has the ten keys only
    validate(old)
    bad = json.loads(json.dumps(model))
    bad["totals"]["lengths_ft"]["surprise"] = 1.0
    with pytest.raises(ModelError):
        validate(bad)
    short = json.loads(json.dumps(model))
    del short["totals"]["lengths_ft"]["eave"]
    with pytest.raises(ModelError):
        validate(short)
    wrong = json.loads(json.dumps(model))
    wrong["totals"]["lengths_ft"]["level_change"] = 5.0  # a new key must match the edges too
    with pytest.raises(ModelError):
        validate(wrong)


def test_the_saved_0_2_example_envelopes_still_validate():
    from conftest import FIXTURES

    names = sorted(FIXTURES.glob("roof_measurement_0.2_*.json"))
    assert len(names) == 4
    for path in names:
        env = json.loads(path.read_text())
        validate(env["model"])
        assert set(env["model"]["totals"]["lengths_ft"]) >= set(CORE_EDGE_TYPES)


def check_one_area(env_totals, model_totals):
    t = env_totals
    priced = t["planes_surface_area_sqft"]
    assert t["area_sqft"] == priced and t["squares"] * 100 == pytest.approx(priced, abs=0.5)
    assert t["roofing_pitched_sqft"] + t["roofing_flat_sqft"] == pytest.approx(priced, abs=0.05)
    assert t["roofing_pitched_squares"] + t["roofing_flat_squares"] == pytest.approx(priced / 100, abs=0.011)
    assert t["area_sqft_wall_line"] - 0.5 <= priced <= t["area_sqft_roof_edge"] + 0.5
    assert model_totals["total_area_sqft"] == pytest.approx(t["area_sqft_roof_edge"], abs=0.2)  # the model is the drawn roof
    assert "DRAWN" in model_totals["note"]


@pytest.mark.parametrize("name", [n for n in _cases() if n.endswith(("_d8", "_d16"))])
def test_the_envelope_has_one_priced_area_on_every_synthetic_case(name):
    model, res = model_of(name)
    totals = {**adapter.engine_totals(res)}
    env = build_envelope(model, method_used="lidar_skeleton", footprint_source="lariac",
                         verification={"verdict": "unverified", "notes": [], "adjustments": [], "original_totals": {}, "model": None,
                                       "rounds": 0, "usage": {"input_tokens": 0, "output_tokens": 0}},
                         warnings=[], warning_codes=[], density_pts_m2=8.0, assessment=assess_engine(res, model, []))
    check_one_area(env["totals"], env["model"]["totals"])
    assert totals["area_sqft"] == env["totals"]["area_sqft"]


def test_the_shipped_example_has_one_priced_area():
    from conftest import FIXTURES

    env = json.loads((FIXTURES / "roof_engine" / "roof_measurement_0.4_engine.json").read_text())
    check_one_area(env["totals"], env["model"]["totals"])
