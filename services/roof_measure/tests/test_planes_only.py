"""The safety net: when the simple roof model cannot be built, the measured LiDAR planes are returned instead.

The failing model is real: a jagged hip block (``fixtures/jagged_hip_unfixable.json``, invented 40 x 24 ft frame) whose
spike facet is no sliver, so ``model.validate`` rejects it. The LiDAR planes are the synthetic hip rectangle's.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import spike_cases
from quality_helpers import hip_rectangle

from roof_measure import pipeline
from roof_measure.classify import Classification
from roof_measure.envelope import TOTALS_KEYS, WARNING_CODES
from roof_measure.library import MeasureError, measure
from roof_measure.model import ModelError, validate
from roof_measure.planes_only import WARNING
from roof_measure.version import PIPELINE_VERSION

KW = {"lat": 1.0, "lng": 1.0, "verify": False, "isolate": False}
PLANE_TOTALS = {"planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "plane_count"}


@pytest.fixture
def unfixable(monkeypatch):
    """The classifier answers with the jagged block whose model validate rejects."""
    rb = spike_cases.roof_block(spike_cases.UNFIXABLE)
    monkeypatch.setattr(pipeline, "classify_blocks", lambda bs, **kw: Classification(blocks=[rb]))


def blocks_file(tmp_path: Path, with_planes: bool = True) -> Path:
    bs = hip_rectangle()
    if not with_planes:
        bs.blocks = []
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "blocks.json"
    bs.save(path)
    return path


def run(tmp_path: Path, method="lidar_skeleton", **kw) -> dict:
    return measure("", method=method, cache_dir=tmp_path / "cache", blocks_path=blocks_file(tmp_path), **KW, **kw)


def test_the_fixture_model_really_fails_validation(unfixable):
    with pytest.raises(ModelError, match="spike"):
        spike_cases.build(spike_cases.UNFIXABLE)


@pytest.mark.parametrize("method", ["lidar_skeleton", "auto"])
def test_a_model_that_cannot_be_built_returns_the_planes(tmp_path, unfixable, method):
    e = run(tmp_path, method)
    m, t, q = e["model"], e["totals"], e["model"]["quality"]
    assert e["method_used"] == "lidar_skeleton" and e["pipeline_version"] == PIPELINE_VERSION
    assert (m["facets"], m["edges"], m["blocks"]) == ([], [], []) and m["source"]["planes_only"] is True
    validate(m)  # the model is a valid 0.1 model, no loosened rule
    assert len(m["planes"]) == 4 and m["confidence"]["overall"] == "low"
    assert q["plane_mismatch_pct"] is None and q["model_uncovered_pct"] == 100.0 and q["facets_model"] == 0
    assert q["planes_lidar"] == 4 and q["reasons"][0] == "model_failed" and "multi_plane_simplified" not in q["reasons"]
    assert set(TOTALS_KEYS) <= set(t) and PLANE_TOTALS <= set(t)  # every old key and the four plane totals
    assert t["area_sqft"] == t["planes_surface_area_sqft"] > 0 and t["squares"] == pytest.approx(t["area_sqft"] / 100)
    assert t["predominant_pitch"] == 4.0 and t["facets"] == 0
    assert t["eave_ft"] == t["drip_edge_eave_ft"] == t["drip_edge_eave_rake_ft"] == t["outline_perimeter_ft"] > 0
    assert [t[k] for k in ("rake_ft", "ridge_ft", "hip_ft", "valley_ft", "step_flashing_ft", "ridge_cap_ridge_ft",
                           "ridge_cap_ridge_hip_ft")] == [0.0] * 7
    assert "model_failed" in WARNING_CODES
    codes, warns = e["warning_codes"], e["warnings"]
    assert codes[warns.index(WARNING)] == "model_failed" and len(codes) == len(warns)
    v = e["verification"]
    assert v["verdict"] == "unverified" and v["rounds"] == 0 and v["model"] is None and v["adjustments"] == []
    assert any("no edges to verify" in n for n in v["notes"])
    assert v["original_totals"]["area_sqft"] == t["area_sqft"] and set(v["original_totals"]) == set(TOTALS_KEYS)
    assert 0.0 < e["confidence"] <= 0.5
    json.dumps(e, allow_nan=False)


def test_it_also_works_with_verification_asked_for(tmp_path, unfixable):
    e = measure("", method="lidar_skeleton", cache_dir=tmp_path / "cache", blocks_path=blocks_file(tmp_path),
                lat=1.0, lng=1.0, verify=True, isolate=False)
    assert e["model"]["source"]["planes_only"] and e["verification"]["verdict"] == "unverified"


def test_the_planes_are_those_of_a_working_measurement(tmp_path, monkeypatch):
    working = run(tmp_path)
    rb = spike_cases.roof_block(spike_cases.UNFIXABLE)
    monkeypatch.setattr(pipeline, "classify_blocks", lambda bs, **kw: Classification(blocks=[rb]))
    net = run(tmp_path / "net")
    assert net["model"]["planes"] == working["model"]["planes"]
    assert net["totals"]["planes_surface_area_sqft"] == working["totals"]["planes_surface_area_sqft"]


def test_an_empty_classification_with_planes_returns_the_planes(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "classify_blocks", lambda bs, **kw: Classification(blocks=[]))
    e = run(tmp_path)
    assert e["model"]["source"]["planes_only"] and e["totals"]["area_sqft"] > 0
    assert "no roof block survived" in " ".join(e["model"]["confidence"]["notes"])


def test_no_planes_still_raises_the_model_error(tmp_path, unfixable):
    with pytest.raises(MeasureError) as err:
        measure("", method="lidar_skeleton", cache_dir=tmp_path / "cache", blocks_path=blocks_file(tmp_path, False),
                **KW)
    assert err.value.code == "measurement_failed" and "spike" in err.value.message


def test_planes_that_all_lie_outside_the_footprint_still_raise(tmp_path, unfixable):
    bs = hip_rectangle()
    bs.footprint_ft = [(500.0, 500.0), (540.0, 500.0), (540.0, 524.0), (500.0, 524.0)]
    path = tmp_path / "far.json"
    bs.save(path)
    with pytest.raises(MeasureError) as err:
        measure("", method="lidar_skeleton", cache_dir=tmp_path / "cache", blocks_path=path, **KW)
    assert err.value.code == "measurement_failed"


def test_a_working_roof_never_takes_the_net(tmp_path):
    e = run(tmp_path)
    assert "planes_only" not in e["model"]["source"] and "model_failed" not in e["warning_codes"]
    assert e["totals"]["facets"] > 0 and "model_failed" not in e["model"]["quality"]["reasons"]


def test_a_failed_agent_whose_rule_fallback_fails_too_returns_the_planes(tmp_path, unfixable):
    from test_agent_fallback import Client, api_error

    res = pipeline.run_pipeline("x", tmp_path / "out", "lidar_agent", blocks_path=blocks_file(tmp_path),
                                client=Client(api_error()), verify=False, render=False)
    e = res.envelope
    assert e["model"]["source"]["planes_only"] and e["method_used"] == "lidar_skeleton"
    assert {"agent_failed_fell_back", "model_failed"} <= set(e["warning_codes"])
    assert e["model"]["quality"]["reasons"][0] == "model_failed" and "agent_failed_fell_back" in e["model"]["quality"]["reasons"]


def test_solar_agent_has_no_planes_and_keeps_raising(tmp_path, monkeypatch):
    from conftest import FIXTURES

    def boom(*a, **kw):
        raise ModelError("facet f1 has a spike (3.0 deg) at vertex 0")

    monkeypatch.setattr(pipeline, "build_model", boom)
    with pytest.raises(ModelError):
        pipeline.run_pipeline("x", tmp_path / "o", "solar_agent", blocks_path=blocks_file(tmp_path, False),
                              solar_fixture=FIXTURES / "synthetic_solar_response.json", no_agent=True, verify=False,
                              render=False)


def test_the_model_file_and_the_envelope_agree(tmp_path, unfixable):
    res = pipeline.run_pipeline("x", tmp_path / "out", "lidar_skeleton", blocks_path=blocks_file(tmp_path),
                                verify=False)  # render left on: a planes-only result has no picture and no warning
    assert "png" not in res.paths and "other" not in res.envelope["warning_codes"]
    on_disk = json.loads(res.paths["model"].read_text())
    assert on_disk["source"]["planes_only"] and on_disk["quality"] == res.envelope["model"]["quality"]


# ---- the committed example the Dart packages parse
EXAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "roof_planes_only" / "roof_measurement_0.3_planes_only.json"


def test_the_example_envelope_is_regenerated_byte_for_byte_and_has_the_documented_shape(tmp_path):
    from roof_measure.synth_envelopes import PLANES_ONLY_DIR, PLANES_ONLY_NAME, generate_all

    generate_all(tmp_path)
    assert (tmp_path / PLANES_ONLY_DIR / f"{PLANES_ONLY_NAME}.json").read_bytes() == EXAMPLE.read_bytes()
    e = json.loads(EXAMPLE.read_text())
    assert EXAMPLE.stat().st_size <= 100_000 and "@" not in EXAMPLE.read_text()
    validate(e["model"])
    assert e["model"]["facets"] == [] and e["model"]["source"]["planes_only"] and e["warning_codes"] == ["model_failed"]
    assert set(TOTALS_KEYS) | PLANE_TOTALS == set(e["totals"])


def test_the_pipeline_result_has_the_example_s_shape(tmp_path, unfixable):
    got, example = run(tmp_path), json.loads(EXAMPLE.read_text())
    assert got["model"]["planes"] == example["model"]["planes"]
    assert got["totals"] == example["totals"]
    assert got["model"]["quality"] == example["model"]["quality"]
    assert set(got) == set(example) and set(got["model"]) == set(example["model"])
    assert got["verification"] == example["verification"]
