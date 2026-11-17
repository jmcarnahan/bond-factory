"""The optional 0.3 envelope keys: present with LiDAR blocks, absent without; every old key unchanged."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from quality_helpers import HERE, ROOT, SITE1, TWO_LEVEL, hip_rectangle

from roof_measure import pipeline
from roof_measure.library import measure
from roof_measure.model import validate
from roof_measure.pipeline import run_pipeline
from roof_measure.version import PIPELINE_VERSION

SOLAR = ROOT / "fixtures" / "synthetic_solar_response.json"
NEW_TOTALS = {"planes_surface_area_sqft", "planes_pitch_weighted", "outline_perimeter_ft", "plane_count"}
KW = {"lat": 1.0, "lng": 1.0, "verify": False, "isolate": False}


def env(tmp_path: Path, blocks: Path = SITE1, **kw) -> dict:
    return measure("", method="lidar_skeleton", cache_dir=tmp_path / "cache", blocks_path=blocks, **KW, **kw)


def without_new(e: dict) -> dict:
    e = copy.deepcopy(e)
    for k in ("quality", "planes"):
        e["model"].pop(k, None)
    for k in NEW_TOTALS:
        e["totals"].pop(k, None)
    e.pop("generated_at")
    e["model"].pop("generated_at")
    return e


@pytest.mark.parametrize("blocks", [SITE1, TWO_LEVEL])
def test_lidar_blocks_add_quality_planes_and_four_totals(tmp_path, blocks):
    e = env(tmp_path, blocks)
    m = e["model"]
    assert set(m["quality"]) == {"plane_mismatch_pct", "outline_covered_pct", "model_uncovered_pct", "level_spread_ft",
                         "planes_lidar", "facets_model", "reasons"}
    assert m["quality"]["planes_lidar"] == len(m["planes"]) == e["totals"]["plane_count"]
    assert m["quality"]["facets_model"] == e["totals"]["facets"] == len(m["facets"])
    assert NEW_TOTALS <= set(e["totals"]) and e["totals"]["planes_surface_area_sqft"] > 0
    assert e["method_used"] == "lidar_skeleton"
    for p in m["planes"]:
        assert {"id", "polygon", "pitch_rise", "aspect_deg", "plan_area_sqft", "surface_area_sqft", "height_ft",
                "rms_ft", "filled_pct"} <= set(p)
    json.dumps(e, allow_nan=False)
    validate(m)  # the model still validates with the extra keys


def test_the_old_keys_and_values_do_not_change(tmp_path, monkeypatch):
    with_q = env(tmp_path)
    monkeypatch.setattr(pipeline, "_assess", lambda *a, **k: None)  # what the 0.2 pipeline did
    plain = env(tmp_path)
    assert "quality" not in plain["model"] and not NEW_TOTALS & set(plain["totals"])
    assert without_new(with_q) == without_new(plain)
    assert list(plain["totals"]) == list(with_q["totals"])[:14]


# The 14 totals and the confidence exactly as pipeline 0.2.0 (commit d7a7d34) produced them, pasted from a run of
# `git archive HEAD` on the same blocks files: any drift in an old digit fails here, whatever else changes.
OLD_0_2_0 = {
    "site1": (SITE1, {
        "area_sqft": 6759.552, "squares": 67.596, "eave_ft": 203.384, "rake_ft": 26.056, "ridge_ft": 3.114,
        "hip_ft": 87.735, "valley_ft": 0.0, "step_flashing_ft": 9.953, "predominant_pitch": 0.0, "facets": 8,
        "drip_edge_eave_ft": 203.384, "drip_edge_eave_rake_ft": 229.44, "ridge_cap_ridge_ft": 3.114,
        "ridge_cap_ridge_hip_ft": 90.849}),
    "two_level": (TWO_LEVEL, {
        "area_sqft": 1999.06, "squares": 19.991, "eave_ft": 174.714, "rake_ft": 0.0, "ridge_ft": 1.754,
        "hip_ft": 124.016, "valley_ft": 0.0, "step_flashing_ft": 0.0, "predominant_pitch": 4.0, "facets": 4,
        "drip_edge_eave_ft": 174.714, "drip_edge_eave_rake_ft": 174.714, "ridge_cap_ridge_ft": 1.754,
        "ridge_cap_ridge_hip_ft": 125.77}),
}


@pytest.mark.parametrize("name", sorted(OLD_0_2_0))
def test_the_old_totals_are_exactly_what_0_2_0_produced(tmp_path, name):
    blocks, old = OLD_0_2_0[name]
    e = env(tmp_path, blocks)
    assert {k: e["totals"][k] for k in old} == old and list(e["totals"])[:14] == list(old)
    assert e["confidence"] == 0.5 and e["warning_codes"] == ["verifier_unverified"]


def test_the_two_level_roof_is_flagged_in_the_envelope(tmp_path):
    q = env(tmp_path, TWO_LEVEL)["model"]["quality"]
    assert "multi_plane_simplified" in q["reasons"] and q["plane_mismatch_pct"] >= 30.0


def test_a_plain_hip_has_no_reasons(tmp_path):
    p = tmp_path / "hip.json"
    hip_rectangle().save(p)
    q = env(tmp_path, p)["model"]["quality"]
    assert q["plane_mismatch_pct"] == 0.0 and q["reasons"] == []


def test_the_keys_are_absent_for_the_solar_method(tmp_path):
    res = run_pipeline("1 Test St", tmp_path / "o", "solar_agent", no_agent=True, blocks_path=SITE1,
                       solar_fixture=SOLAR, verify=False, render=False)
    e = res.envelope
    assert e["method_used"] == "solar_agent"
    assert "quality" not in e["model"] and "planes" not in e["model"] and not NEW_TOTALS & set(e["totals"])
    assert len(e["totals"]) == 14


def test_the_keys_are_absent_when_there_are_no_blocks(tmp_path):
    from quality_helpers import blockset

    p = tmp_path / "empty.json"
    blockset([(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)], []).save(p)
    e = env(tmp_path, p)
    assert e["totals"]["facets"] == 0 and "quality" not in e["model"] and not NEW_TOTALS & set(e["totals"])


def test_a_quality_failure_never_fails_the_measurement_and_says_so(tmp_path, monkeypatch, caplog):
    from roof_measure import quality

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(quality, "assess", boom)
    e = env(tmp_path)
    q = e["model"]["quality"]
    assert q["reasons"] == ["quality_failed"] and q["plane_mismatch_pct"] is None and q["outline_covered_pct"] is None
    assert q["facets_model"] == len(e["model"]["facets"]) and "planes" not in e["model"]
    assert not NEW_TOTALS & set(e["totals"]) and e["totals"]["area_sqft"] > 0
    assert any("quality assessment failed" in r.message and r.exc_info for r in caplog.records)  # the cause is logged


def test_snapping_that_fails_reports_quality_failed(tmp_path, monkeypatch):
    from roof_measure import planes, quality

    monkeypatch.setattr(quality, "snap_with_stats", lambda *a, **k: planes.SnapResult(failed=True))
    e = env(tmp_path)
    assert e["model"]["quality"]["reasons"] == ["quality_failed"] and "planes" not in e["model"]


def test_no_surviving_plane_still_reports_coverage(tmp_path):
    from quality_helpers import block, blockset

    far = block("far", [(500, 500), (520, 500), (520, 520), (500, 520)])  # a LiDAR plane far from the outline
    p = tmp_path / "far.json"
    blockset([(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)], [far]).save(p)
    e = env(tmp_path, p)
    q = e["model"]["quality"]
    assert q["outline_covered_pct"] == 0.0 and q["plane_mismatch_pct"] is None and q["planes_lidar"] == 0
    assert "low_outline_coverage" in q["reasons"]
    assert e["model"]["planes"] == [] and not NEW_TOTALS & set(e["totals"])


def test_street_match_coverage_is_measured_on_the_footprint(tmp_path, monkeypatch):
    """Unclipped planes would cover 100% of themselves; coverage must still be judged against the footprint."""
    from quality_helpers import block, blockset

    half = block("half", [(0, 0), (20, 0), (20, 8), (0, 8)])
    p = tmp_path / "half.json"
    blockset([(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)], [half]).save(p)
    from roof_measure import pipeline_notes

    real = pipeline_notes.collect_warnings
    monkeypatch.setattr(pipeline, "collect_warnings", lambda m, fp, *a, **k: real(
        m, {**fp, "warnings": ["w"], "codes": ["parcel_street_match"]}, *a, **k))
    q = env(tmp_path, p)["model"]["quality"]
    assert q["outline_covered_pct"] == 40.0 and "low_outline_coverage" in q["reasons"]
    assert "parcel_street_match" in q["reasons"]


def test_a_crash_retry_adds_the_fallback_reason_to_quality(monkeypatch):
    from roof_measure import _isolate, library

    quality = {"plane_mismatch_pct": 0.0, "outline_covered_pct": 90.0, "planes_lidar": 1, "facets_model": 1,
               "reasons": ["parcel_street_match"]}
    monkeypatch.setattr(_isolate, "run_isolated", lambda req, on_stage, grace: {
        "warnings": [], "warning_codes": [], "model": {"quality": quality}, "method_used": "lidar_skeleton"})
    crash = library.MeasureError("measurement_failed")
    req = {"method": "lidar_agent", "deadline_s": 180.0}
    out = library._retry_after_crash(req, None, crash, library.time.monotonic())
    assert out["warning_codes"] == ["agent_failed_fell_back"]
    assert out["model"]["quality"]["reasons"] == ["parcel_street_match", "agent_failed_fell_back"]
    bare = {"warnings": [], "warning_codes": [], "model": {}, "method_used": "lidar_skeleton"}  # no quality: no crash
    monkeypatch.setattr(_isolate, "run_isolated", lambda req, on_stage, grace: bare)
    assert library._retry_after_crash(req, None, crash, library.time.monotonic())["model"] == {}


def test_the_model_file_carries_the_same_keys(tmp_path):
    res = run_pipeline("1 Test St", tmp_path / "o", "lidar_skeleton", blocks_path=SITE1, verify=False, render=False)
    on_disk = json.loads(res.paths["model"].read_text())
    assert on_disk["quality"] == res.envelope["model"]["quality"] and len(on_disk["planes"]) == len(res.envelope["model"]["planes"])


def test_pipeline_version_is_0_3_0_and_the_contract_name_is_unchanged():
    from roof_measure.version import CONTRACT

    assert PIPELINE_VERSION == "0.3.0" and CONTRACT == "bond.roof_model/0.2"


def test_street_match_note_is_a_reason_code(tmp_path, monkeypatch):
    """A street-only parcel match: the warning code is parcel_street_match and it is a quality reason."""
    from roof_measure import pipeline_notes

    real = pipeline_notes.collect_warnings

    def with_street(model, fpinfo, *a, **k):
        fpinfo = {**fpinfo, "warnings": ["no exact parcel match; used parcel X (street match)."],
                  "codes": ["parcel_street_match"]}
        return real(model, fpinfo, *a, **k)

    monkeypatch.setattr(pipeline, "collect_warnings", with_street)
    e = env(tmp_path)
    assert "parcel_street_match" in e["warning_codes"] and "other" not in e["warning_codes"]
    assert "parcel_street_match" in e["model"]["quality"]["reasons"]


def test_clipping_follows_the_street_match_code(tmp_path, monkeypatch):
    from roof_measure import pipeline_notes

    base = env(tmp_path)  # no street match: clipped
    real = pipeline_notes.collect_warnings
    monkeypatch.setattr(pipeline, "collect_warnings", lambda m, fp, *a, **k: real(
        m, {**fp, "warnings": ["w"], "codes": ["parcel_street_match"]}, *a, **k))
    street = env(tmp_path)

    def covered(e):
        return sum(p["plan_area_sqft"] for p in e["model"]["planes"])

    assert covered(street) < covered(base) - 100.0  # the unclipped planes stop at the raw planes: smaller
    assert street["totals"]["outline_perimeter_ft"] != base["totals"]["outline_perimeter_ft"]


def test_eval_harness_runs_on_the_fixtures_dir(tmp_path):
    out = tmp_path / "svg"
    r = subprocess.run([sys.executable, "-m", "tools.eval_blocks", str(HERE / "fixtures"), str(ROOT / "fixtures"),
                        "--svg", str(out), "--json", str(tmp_path / "m.json")], cwd=HERE.parent, check=False,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0].split()[:3] == ["file", "planes", "facets"]
    assert any(ln.startswith("two_level_l_blocks.json") and "multi_plane_simplified" in ln for ln in lines)
    assert any(ln.startswith("site1_blocks.json") for ln in lines)
    assert (out / "two_level_l_blocks.svg").read_text().startswith("<svg") and "sq ft" in (out / "two_level_l_blocks.svg").read_text()
    rows = json.loads((tmp_path / "m.json").read_text())
    assert {r["file"] for r in rows} >= {"two_level_l_blocks.json", "site1_blocks.json"}
    assert not any(ln.startswith("roof_measurement") for ln in lines)  # envelope fixtures are skipped


def test_a_non_finite_block_is_dropped_with_a_reason_and_the_rest_is_judged(tmp_path):
    import json

    d = json.loads(TWO_LEVEL.read_text())
    d["blocks"][0]["polygon_ft"][0][0] = float("nan")
    d["blocks"][1]["pitch_rise"] = float("inf")
    p = tmp_path / "nan.json"
    p.write_text(json.dumps(d))  # json.dumps writes NaN/Infinity, which BlockSet.load reads back
    from roof_measure.classify import BlockSet
    from roof_measure.quality import assess

    bs = BlockSet.load(p)
    a = assess(bs, {"facets": []}, [])
    assert a is not None and "bad_lidar_block" in a["quality"]["reasons"]
    assert len(a["planes"]) == 6
    json.dumps(a, allow_nan=False)  # nothing non-finite leaks into the envelope part


def test_only_non_finite_blocks_still_give_a_quality_object():
    from quality_helpers import block, blockset

    from roof_measure.quality import assess

    bad = block("bad", [(0, 0), (10, 0), (10, 10), (0, 10)])
    bad["polygon_ft"][2][1] = float("nan")
    a = assess(blockset([(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)], [bad]), {"facets": []}, [])
    q = a["quality"]
    assert q["outline_covered_pct"] == 0.0 and a["planes"] == [] and "bad_lidar_block" in q["reasons"]
    assert "low_outline_coverage" in q["reasons"]
