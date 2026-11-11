"""Method resolution (plan D12) and the pipeline's envelope, stage callbacks and deadline."""

import pytest
from conftest import FIXTURES

from roof_measure import pipeline
from roof_measure.blocks import BlocksError
from roof_measure.deadline import Deadline, DeadlineExceeded
from roof_measure.footprint_types import FootprintError
from roof_measure.lidar import LidarError, LidarTooSparse
from roof_measure.pipeline_notes import collect_warnings

BLOCKS = FIXTURES / "site1_blocks.json"


@pytest.fixture
def keys(monkeypatch):
    def setter(solar: bool, anthropic: bool):
        for name in ("GOOGLE_SOLAR_API_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        if solar:
            monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "k")
        if anthropic:
            monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    return setter


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_run(address, out_dir, method, **kw):
        seen.append((method, kw["fallback_from"]))
        if method == "lidar_skeleton" and fake_run.error:
            raise fake_run.error
        return method

    fake_run.error = None
    monkeypatch.setattr(pipeline, "_run", fake_run)
    return fake_run, seen


def test_auto_uses_lidar_first_and_stops_there(calls, keys, tmp_path):
    keys(True, True)
    _, seen = calls
    assert pipeline.run_pipeline("x", tmp_path, "auto") == "lidar_skeleton"
    assert seen == [("lidar_skeleton", None)]


@pytest.mark.parametrize("err", [LidarError("No USGS 3DEP LiDAR project covers this address."),
                                 LidarTooSparse("P", 2020, 3.0, 8.0)])
def test_lidar_failure_falls_back_to_solar_agent_with_both_keys(calls, keys, tmp_path, err):
    keys(True, True)
    run, seen = calls
    run.error = err
    assert pipeline.run_pipeline("x", tmp_path, "auto") == "solar_agent"
    assert seen == [("lidar_skeleton", None), ("solar_agent", "lidar_skeleton")]


@pytest.mark.parametrize("solar,anthropic", [(False, False), (True, False), (False, True)])
def test_without_both_keys_the_lidar_error_is_the_answer(calls, keys, tmp_path, solar, anthropic):
    keys(solar, anthropic)
    run, seen = calls
    run.error = LidarError("none")
    with pytest.raises(LidarError):
        pipeline.run_pipeline("x", tmp_path, "auto")
    assert seen == [("lidar_skeleton", None)]


@pytest.mark.parametrize("err", [FootprintError("none"), BlocksError("No roof block survived segmentation")])
def test_other_errors_do_not_trigger_the_fallback(calls, keys, tmp_path, err):
    keys(True, True)
    run, seen = calls
    run.error = err
    with pytest.raises(type(err)):
        pipeline.run_pipeline("x", tmp_path, "auto")
    assert seen == [("lidar_skeleton", None)]


def test_explicit_methods_never_fall_back_and_unknown_is_rejected(calls, keys, tmp_path):
    keys(True, True)
    run, seen = calls
    run.error = LidarError("none")
    with pytest.raises(LidarError):
        pipeline.run_pipeline("x", tmp_path, "lidar_skeleton")
    assert seen == [("lidar_skeleton", None)]
    assert pipeline.run_pipeline("x", tmp_path, "lidar_agent") == "lidar_agent"
    with pytest.raises(pipeline.PipelineError):
        pipeline.run_pipeline("x", tmp_path, "bogus")


def test_fallback_adds_the_method_fallback_warning():
    model = {"warnings": []}
    fp = {"codes": ["footprint_osm"], "warnings": ["osm"], "other_buildings": 0}
    w, c = collect_warnings(model, fp, {"verdict": "unverified"}, 5.0, "lidar_skeleton", "solar_agent")
    assert "5.0 points/m2" in w[1]
    assert c == ["footprint_osm", "low_point_density", "method_fallback", "solar_segments_only", "verifier_unverified"]
    assert len(w) == len(c)
    w, c = collect_warnings({"warnings": ["model note"]}, {"codes": [], "warnings": [], "other_buildings": 2},
                            {"verdict": "adjusted"}, 20.0, None, "lidar_skeleton")
    assert c == ["other_buildings_on_parcel", "other", "verifier_adjusted"]


def test_pipeline_from_blocks_returns_an_envelope_and_reports_stages(tmp_path, keys):
    keys(False, False)
    stages = []
    res = pipeline.run_pipeline("100 Example Ave, Sampletown, CA 90000", tmp_path, "auto", blocks_path=BLOCKS,
                                on_stage=stages.append)
    assert res.method_used == "lidar_skeleton" and res.footprint_source == "lariac"
    assert res.envelope["contract"] == "bond.roof_model/0.2" and res.verification["verdict"] == "unverified"
    assert res.density_pts_m2 == pytest.approx(19.7) and res.envelope["model"] is res.model
    assert stages == ["model", "verify", "render"]
    assert res.envelope["totals"]["area_sqft"] == pytest.approx(res.model["totals"]["total_area_sqft"], abs=0.01)
    assert "model.json" in " ".join(p.name for p in res.paths.values())


def test_expired_deadline_stops_the_pipeline(tmp_path):
    with pytest.raises(DeadlineExceeded):
        pipeline.run_pipeline("x", tmp_path, "lidar_skeleton", blocks_path=BLOCKS, deadline=Deadline.after(0))


def test_verify_false_skips_the_verifier(tmp_path, keys):
    keys(False, False)
    stages = []
    res = pipeline.run_pipeline("x", tmp_path, "lidar_skeleton", blocks_path=BLOCKS, verify=False,
                                on_stage=stages.append)
    assert "verify" not in stages and "not requested" in res.verification["notes"][0]


def test_a_verifier_crash_never_fails_the_job(tmp_path, monkeypatch, keys):
    keys(False, False)
    import roof_measure.verify as v

    def boom(*a, **k):
        raise RuntimeError("verifier bug")

    monkeypatch.setattr(v, "verify", boom)
    res = pipeline.run_pipeline("x", tmp_path, "lidar_skeleton", blocks_path=BLOCKS)
    assert res.verification["verdict"] == "unverified" and "could not run" in res.verification["notes"][0]


def test_parse_address_label():
    a = pipeline.parse_address("100 Example Ave, Sampletown, CA 90000")
    assert (a.line1, a.city, a.state, a.zip) == ("100 Example Ave", "Sampletown", "CA", "90000")
    assert pipeline.parse_address("just a label").line1 == "just a label"


def test_low_density_warning_threshold_is_8_and_hard_floor_is_4():
    from roof_measure import lidar

    assert lidar.MIN_ROOF_DENSITY == 4.0
    fp = {"codes": [], "warnings": [], "other_buildings": 0}
    for density, warned in ((7.7, True), (8.0, False), (12.0, False), (None, False)):
        _, c = collect_warnings({"warnings": []}, fp, {"verdict": "pass"}, density, None, "lidar_skeleton")
        assert ("low_point_density" in c) is warned, density
