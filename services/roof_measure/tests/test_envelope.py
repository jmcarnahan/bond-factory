"""The 0.2 envelope: 14 totals keys, variants, the confidence rule, warning codes."""

import json

import pytest
from conftest import FIXTURES

from roof_measure.envelope import (
    TOTALS_KEYS,
    WARNING_CODES,
    build_envelope,
    confidence_score,
    totals_from_model,
)
from roof_measure.version import CONTRACT, PIPELINE_VERSION

HIP = json.loads((FIXTURES / "synthetic_hip.json").read_text())
VERIF = {"verdict": "pass", "notes": [], "adjustments": [], "original_totals": {}, "model": None, "rounds": 0,
         "usage": {"input_tokens": 0, "output_tokens": 0}}


def env(model=HIP, **kw):
    args = {"method_used": "lidar_skeleton", "footprint_source": "osm", "verification": VERIF, "warnings": [],
            "warning_codes": []} | kw
    return build_envelope(model, **args)


@pytest.mark.parametrize("name", ["synthetic_hip", "synthetic_gable", "synthetic_flat_parapet", "synthetic_flat_curbs",
                                  "synthetic_hip_zigzag"])
def test_totals_have_exactly_the_14_keys_and_match_the_model(name):
    m = json.loads((FIXTURES / f"{name}.json").read_text())
    t = totals_from_model(m)
    assert tuple(t) == TOTALS_KEYS and len(t) == 14
    L = m["totals"]["lengths_ft"]
    assert t["area_sqft"] == pytest.approx(m["totals"]["total_area_sqft"], abs=0.001)
    assert t["squares"] == pytest.approx(m["totals"]["squares"], abs=0.001)
    assert t["facets"] == len(m["facets"])
    for key, edge in (("eave_ft", "eave"), ("rake_ft", "rake"), ("ridge_ft", "ridge"), ("hip_ft", "hip"),
                      ("valley_ft", "valley"), ("step_flashing_ft", "step_flashing")):
        assert t[key] == pytest.approx(L[edge], abs=0.001)
    # the totals are sums of the edges, not just copies of model.totals
    for edge in ("eave", "ridge", "hip", "rake"):
        assert t[f"{edge}_ft"] == pytest.approx(sum(e["length_ft"] for e in m["edges"] if e["type"] == edge), abs=0.05)


def test_variant_arithmetic():
    gable = json.loads((FIXTURES / "synthetic_gable.json").read_text())
    t = totals_from_model(gable)
    assert t["rake_ft"] > 0 and t["ridge_ft"] > 0
    assert t["drip_edge_eave_ft"] == t["eave_ft"]
    assert t["drip_edge_eave_rake_ft"] == pytest.approx(t["eave_ft"] + t["rake_ft"], abs=0.002)
    assert t["ridge_cap_ridge_ft"] == t["ridge_ft"]
    assert t["ridge_cap_ridge_hip_ft"] == pytest.approx(t["ridge_ft"] + t["hip_ft"], abs=0.002)
    h = totals_from_model(HIP)
    assert h["ridge_cap_ridge_hip_ft"] == pytest.approx(9.0 + h["hip_ft"], abs=0.002) and h["predominant_pitch"] == 4.0
    flat = totals_from_model(json.loads((FIXTURES / "synthetic_flat_parapet.json").read_text()))
    assert flat["predominant_pitch"] == 0 and flat["eave_ft"] == 0


@pytest.mark.parametrize("overall,source,verdict,density,want", [
    ("high", "lariac", "pass", None, 0.9), ("medium", "lariac", "pass", 20.0, 0.7), ("low", "lariac", "pass", 20.0, 0.5),
    ("high", "osm", "pass", None, 0.85), ("medium", "osm", "pass", None, 0.7),
    ("high", "solar", "pass", None, 0.5), ("high", "lidar_hull", "pass", None, 0.5),
    ("high", "lariac", "adjusted", None, 0.85), ("high", "solar", "adjusted", None, 0.45),
    ("high", "lariac", "unverified", None, 0.7), ("low", "lariac", "unverified", None, 0.5),
    ("high", "lariac", "fail", None, 0.3), ("low", "lariac", "fail", None, 0.3),
    ("medium", "osm", "pass", 11.9, 0.6), ("medium", "osm", "pass", 12.0, 0.7),
    ("low", "lidar_hull", "adjusted", 5.0, 0.35), ("low", "lariac", "fail", 1.0, 0.2),
])
def test_confidence_table(overall, source, verdict, density, want):
    assert confidence_score({"confidence": {"overall": overall}}, source, verdict, density) == pytest.approx(want)


def test_confidence_is_clamped():
    assert 0.0 <= confidence_score({"confidence": {"overall": "low"}}, "solar", "fail", 0.0) <= 1.0
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
    for source in ("solar", "lidar_hull"):
        e = env(footprint_source=source)
        assert e["verification"]["verdict"] == "adjusted" and "lowered from pass" in e["verification"]["notes"][-1]
        assert e["confidence"] == 0.45
    assert VERIF["notes"] == [] and VERIF["verdict"] == "pass"  # the caller's dict is not mutated
    assert env(footprint_source="osm")["verification"]["verdict"] == "pass"


def test_bad_verdict_is_rejected():
    with pytest.raises(ValueError):
        env(verification={**VERIF, "verdict": "great"})


def test_warning_code_list_matches_the_contract():
    assert WARNING_CODES == ("footprint_osm", "footprint_solar", "footprint_lidar_hull", "source_unreachable", "parcel_without_building",
                             "other_buildings_on_parcel", "low_point_density", "method_fallback",
                             "verifier_unverified", "verifier_adjusted", "verifier_failed", "verifier_timeout",
                             "solar_segments_only", "flat_roof_assumed", "other")


def test_source_unreachable_code_survives_build_envelope():
    assert "source_unreachable" in WARNING_CODES
    e = env(warnings=["a"], warning_codes=["source_unreachable"])
    assert e["warning_codes"] == ["source_unreachable"]
