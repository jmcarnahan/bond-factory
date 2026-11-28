"""The envelope: the contract-0.6 totals keys, the confidence rule, warning codes. Models come from the engine on synthetic roofs."""

import pytest
from test_engine_adapter import model_of

from roof_measure.envelope import (
    WARNING_CODES,
    build_envelope,
    confidence_score,
    totals_from_model,
)
from roof_measure.model import TOTALS_KEYS
from roof_measure.version import CONTRACT, PIPELINE_VERSION

HIP = model_of("hip_d8")[0]
VERIF = {"verdict": "pass", "notes": [], "adjustments": [], "original_totals": {}, "model": None, "rounds": 0,
         "usage": {"input_tokens": 0, "output_tokens": 0}}


def env(model=HIP, **kw):
    args = {"method_used": "planes", "footprint_source": "osm", "verification": VERIF, "warnings": [],
            "warning_codes": []} | kw
    return build_envelope(model, **args)


@pytest.mark.parametrize("name", ["hip_d8", "gable_d8", "flat_d8", "flat_pitched_step_d8", "l_shape_d8"])
def test_totals_have_exactly_the_contract_keys_and_match_the_model(name):
    m = model_of(name)[0]
    t = totals_from_model(m)
    assert tuple(t) == TOTALS_KEYS == tuple(k for k in m["totals"] if k in TOTALS_KEYS)
    assert t["area_sqft"] == m["totals"]["total_area_sqft"] and t["plane_count"] == len(m["facets"])
    # the totals are sums of the edges, not just copies of model.totals
    for edge in ("eave", "ridge", "hip", "rake", "valley", "step_flashing", "wall_flashing", "flat_edge", "level_change"):
        assert t[f"{edge}_ft"] == pytest.approx(sum(e["length_ft"] for e in m["edges"] if e["type"] == edge), abs=0.05), edge


def test_variant_arithmetic():
    t = totals_from_model(model_of("gable_d8")[0])
    assert t["rake_ft"] > 0 and t["ridge_ft"] > 0 and t["hip_ft"] == 0
    assert t["eave_rake_ft"] == pytest.approx(t["eave_ft"] + t["rake_ft"], abs=0.02)
    assert t["ridge_hip_ft"] == pytest.approx(t["ridge_ft"] + t["hip_ft"], abs=0.02)
    h = totals_from_model(HIP)
    assert h["ridge_hip_ft"] == pytest.approx(h["ridge_ft"] + h["hip_ft"], abs=0.02) and h["hip_ft"] > 0
    flat = totals_from_model(model_of("flat_d8")[0])
    assert flat["roofing_pitched_sqft"] == 0 and flat["ridge_ft"] == 0 and flat["flat_edge_ft"] > 0


@pytest.mark.parametrize("overall,source,verdict,density,want", [
    ("high", "lariac", "pass", None, 0.9), ("medium", "lariac", "pass", 20.0, 0.7), ("low", "lariac", "pass", 20.0, 0.5),
    ("high", "osm", "pass", None, 0.85), ("medium", "osm", "pass", None, 0.7),
    ("high", "lidar_hull", "pass", None, 0.5),
    ("high", "lariac", "adjusted", None, 0.85), ("high", "lidar_hull", "adjusted", None, 0.45),
    ("high", "lariac", "unverified", None, 0.7), ("low", "lariac", "unverified", None, 0.5),
    ("high", "lariac", "fail", None, 0.3), ("low", "lariac", "fail", None, 0.3),
    ("medium", "osm", "pass", 11.9, 0.6), ("medium", "osm", "pass", 12.0, 0.7),
    ("low", "lidar_hull", "adjusted", 5.0, 0.35), ("low", "lariac", "fail", 1.0, 0.2),
])
def test_confidence_table(overall, source, verdict, density, want):
    assert confidence_score({"confidence": {"overall": overall}}, source, verdict, density) == pytest.approx(want)


def test_confidence_is_clamped():
    assert 0.0 <= confidence_score({"confidence": {"overall": "low"}}, "lidar_hull", "fail", 0.0) <= 1.0
    assert confidence_score({"confidence": {}}, "osm", "pass") == 0.5  # unknown overall behaves like low


def test_envelope_shape_and_contract_strings():
    e = env(warnings=["w"], warning_codes=["footprint_osm"], generated_at="2026-01-01T00:00:00Z")
    assert e["contract"] == CONTRACT == "bond.roof_model/0.2" and e["pipeline_version"] == PIPELINE_VERSION
    assert e["generated_at"] == "2026-01-01T00:00:00Z" and e["model"] is HIP
    assert list(e["totals"]) == list(TOTALS_KEYS) and e["confidence"] == 0.7
    assert len(e["warnings"]) == len(e["warning_codes"])


def test_generated_at_defaults_to_utc_now():
    assert env()["generated_at"].endswith("Z")


def test_warnings_and_codes_must_line_up_and_unknown_codes_become_other():
    with pytest.raises(ValueError):
        env(warnings=["a", "b"], warning_codes=["footprint_osm"])
    e = env(warnings=["a", "b"], warning_codes=["footprint_osm", "brand_new_code"])
    assert e["warning_codes"] == ["footprint_osm", "other"] and set(e["warning_codes"]) <= set(WARNING_CODES)


def test_degraded_footprints_can_never_pass():
    for source in ("lidar_hull",):
        e = env(footprint_source=source)
        assert e["verification"]["verdict"] == "adjusted" and "lowered from pass" in e["verification"]["notes"][-1]
        assert e["confidence"] == 0.45
    assert VERIF["notes"] == [] and VERIF["verdict"] == "pass"  # the caller's dict is not mutated
    assert env(footprint_source="osm")["verification"]["verdict"] == "pass"


def test_bad_verdict_is_rejected():
    with pytest.raises(ValueError):
        env(verification={**VERIF, "verdict": "great"})


def test_warning_code_list_matches_the_contract():
    assert WARNING_CODES == ("footprint_osm", "footprint_lidar_hull", "source_unreachable", "parcel_without_building",
                             "other_buildings_on_parcel", "parcel_street_match", "low_point_density", "low_slope_confirm",
                             "outline_mismatch", "poor_fit", "low_density", "objects_failed", "other")  # 0.6.0 removed the codes with no producer


def test_source_unreachable_code_survives_build_envelope():
    assert "source_unreachable" in WARNING_CODES
    e = env(warnings=["a"], warning_codes=["source_unreachable"])
    assert e["warning_codes"] == ["source_unreachable"]
