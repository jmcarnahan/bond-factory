"""The generated 0.2 fixtures: size, placeholder data, schema, arithmetic, determinism, the docs example."""

import json
from pathlib import Path

import pytest
from conftest import FIXTURES

from roof_measure.envelope import TOTALS_KEYS, WARNING_CODES, confidence_score, totals_from_model
from roof_measure.model import validate
from roof_measure.solar import segments_to_evidence
from roof_measure.synth_envelopes import generate_all
from roof_measure.verify_tools import verdict_from_delta

VERDICTS = ["pass", "adjusted", "unverified", "fail"]
MODELS = ["synthetic_flat_curbs", "synthetic_hip_zigzag"]
GENERATED = [f"roof_measurement_0.2_{v}" for v in VERDICTS] + MODELS + ["synthetic_solar_response"]
REPO = Path(__file__).resolve().parents[3]


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize("name", GENERATED)
def test_size_and_placeholder_data(name):
    path = FIXTURES / f"{name}.json"
    assert path.stat().st_size <= 100_000
    text = path.read_text()
    for banned in ("Den" + "ker", "Gar" + "dena", "Roo" + "fr", "@"):  # split so the tree never carries the words
        assert banned not in text


@pytest.mark.parametrize("verdict", VERDICTS)
def test_envelope_shape(verdict):
    e = load(f"roof_measurement_0.2_{verdict}")
    assert e["contract"] == "bond.roof_model/0.2" and e["pipeline_version"] == "0.2.0"
    assert e["generated_at"] == "2026-11-10T00:00:00Z" and e["footprint_source"] in ("lariac", "osm")
    assert e["method_used"] == "lidar_skeleton"
    m = e["model"]
    assert m["schema"] == "bond.roof_model/0.1" and m["address"]["formatted"] == "100 Example Ave, Sampletown, CA 90000"
    assert m["origin"] == {"lat": 0.0, "lng": 0.0}
    validate(m)
    assert tuple(e["totals"]) == TOTALS_KEYS and e["totals"] == totals_from_model(m)
    assert len(e["warnings"]) == len(e["warning_codes"]) and set(e["warning_codes"]) <= set(WARNING_CODES)
    v = e["verification"]
    assert v["verdict"] == verdict and set(v["original_totals"]) == set(TOTALS_KEYS)
    assert v["usage"].keys() == {"input_tokens", "output_tokens"} and isinstance(v["notes"], list) and v["notes"]
    assert e["confidence"] == confidence_score(m, e["footprint_source"], verdict, None)


def test_verdicts_follow_the_totals_delta():
    for verdict in ("pass", "adjusted", "fail"):
        e = load(f"roof_measurement_0.2_{verdict}")
        assert verdict_from_delta(e["verification"]["original_totals"], e["totals"]) == verdict
    u = load("roof_measurement_0.2_unverified")
    assert u["verification"]["model"] is None and u["verification"]["rounds"] == 0
    assert u["verification"]["original_totals"] == u["totals"] and u["warning_codes"] == ["verifier_unverified"]


def test_fail_fixture_is_marked_synthetic_and_8_percent_off():
    e = load("roof_measurement_0.2_fail")
    assert "SYNTHETIC FIXTURE" in e["verification"]["notes"][0]
    ratio = e["verification"]["original_totals"]["area_sqft"] / e["totals"]["area_sqft"]
    assert ratio == pytest.approx(1.08, abs=0.001) and e["confidence"] == 0.3


def test_adjusted_fixture_merged_the_zigzag_eave():
    e, zig = load("roof_measurement_0.2_adjusted"), load("synthetic_hip_zigzag")
    adj = e["verification"]["adjustments"]
    assert len(adj) == 1 and adj[0]["op"] == "merge_collinear" and adj[0]["edge_type"] == "eave"
    assert len(adj[0]["edge_ids"]) == 7 and len(e["model"]["edges"]) == len(zig["edges"]) - 6
    assert e["verification"]["original_totals"] == totals_from_model(zig)
    assert abs(e["totals"]["area_sqft"] - e["verification"]["original_totals"]["area_sqft"]) > 0.5
    assert e["totals"]["eave_ft"] == pytest.approx(122.0, abs=0.01) and e["warning_codes"][-1] == "verifier_adjusted"


def test_zigzag_model_has_seven_south_eave_segments_and_validates():
    m = load("synthetic_hip_zigzag")
    validate(m)
    south = [e for e in m["edges"] if e["type"] == "eave" and e["facets"] == ["f1"]]
    assert len(south) == 7 and sum(1 for e in south if e["length_ft"] < 2.0) == 5
    assert all(abs(p[1]) <= 0.2 for e in south for p in e["points"])


def test_curbs_model():
    m = load("synthetic_flat_curbs")
    validate(m)  # hole outlines may sit inside the facet
    assert len(m["holes"]) == 17 and all(h["kind"] == "chimney" and 2 <= len(h["polygon"]) for h in m["holes"])
    sizes = {w for h in m["holes"] for w in (h["polygon"][1][0] - h["polygon"][0][0], h["polygon"][2][1] - h["polygon"][1][1])}
    assert sizes <= {2.0, 3.0, 4.0}
    walls = [e for e in m["edges"] if e["type"] == "wall_flashing"]
    assert len(walls) == 68 and sum(e["length_ft"] for e in walls) == pytest.approx(m["totals"]["lengths_ft"]["wall_flashing"])
    steps = [e for e in m["edges"] if e["type"] == "step_flashing"]
    assert len(steps) == 1 and steps[0]["length_ft"] == 10.0
    assert m["totals"]["lengths_ft"]["parapet"] == pytest.approx(190.0)  # 200 less the 10 ft of step flashing
    holes = sum(h["area_sqft"] for h in m["holes"])
    assert m["totals"]["total_area_sqft"] == pytest.approx(2400 - holes) and m["facets"][0]["area_sqft"] == pytest.approx(2400 - holes)
    assert m["blocks"][0]["plan_area_sqft"] == pytest.approx(2400 - holes)


def test_solar_response_is_a_buildinginsights_shape_the_service_can_read():
    s = load("synthetic_solar_response")
    assert s["_SYNTHETIC"] is True and s["imageryQuality"] == "HIGH"
    segs = s["solarPotential"]["roofSegmentStats"]
    assert len(segs) == 9 and {"boundingBox", "pitchDegrees", "azimuthDegrees", "stats", "center"} <= set(segs[0])
    assert {"sw", "ne"} == set(segs[0]["boundingBox"]) and "areaMeters2" in segs[0]["stats"]
    blocks = load("site1_blocks")
    rows = segments_to_evidence(s, blocks["frame"], [tuple(p) for p in blocks["footprint_ft"]])
    assert len(rows) == 9 and sum(r["form_hint"] == "sloped" for r in rows) == 6
    assert sum(r["inside_footprint"] for r in rows) >= 7
    assert abs(s["center"]["latitude"]) < 0.01 and abs(s["center"]["longitude"]) < 0.01  # synthetic point near 0/0


def test_regeneration_is_byte_identical(tmp_path):
    generate_all(tmp_path)
    for name in GENERATED:
        assert (tmp_path / f"{name}.json").read_bytes() == (FIXTURES / f"{name}.json").read_bytes(), name


def test_docs_embed_the_pass_envelope_verbatim():
    doc = (REPO / "docs" / "contract-0.2.md").read_text()
    pass_text = (FIXTURES / "roof_measurement_0.2_pass.json").read_text().rstrip("\n")
    assert pass_text in doc
    for code in WARNING_CODES:
        assert f"`{code}`" in doc


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("synthetic_*.json")), ids=lambda p: p.stem)
def test_every_tracked_synthetic_model_passes_validate(path):
    doc = json.loads(path.read_text())
    if doc.get("schema", "").startswith("bond.roof_model/"):
        validate(doc)
