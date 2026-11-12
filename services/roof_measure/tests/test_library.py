"""measure() facade, in process: fixtures only, no network, no real address."""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from conftest import FIXTURES

import roof_measure
from roof_measure import cache, errors, library
from roof_measure.blocks import BlocksError
from roof_measure.deadline import DeadlineExceeded
from roof_measure.footprint_types import AmbiguousBuilding, FootprintError
from roof_measure.geocode import GeocodeError, GeocodeUnavailable
from roof_measure.library import STAGES, MeasureError, measure, purge_cache
from roof_measure.lidar import LidarError, LidarTooSparse

ADDR = "100 Example Ave, Sampletown, CA 90000"
BLOCKS = FIXTURES / "site1_blocks.json"
ENVELOPE_KEYS = set(json.loads((FIXTURES / "roof_measurement_0.2_unverified.json").read_text()))


def call(tmp_path, **kw):
    args = {"method": "lidar_skeleton", "verify": False, "cache_dir": tmp_path / "cache", "blocks_path": BLOCKS,
            "isolate": False}
    return measure(ADDR, **(args | kw))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(cache, "_send", boom)


def test_public_api():
    assert set(roof_measure.__all__) == {"measure", "MeasureError", "purge_cache", "STAGES", "KILL_GRACE_S"}
    assert STAGES == ("geocode", "footprint", "lidar", "blocks", "model", "verify", "render")
    assert library.KILL_GRACE_S == 30.0


def test_happy_path_on_the_blocks_fixture(tmp_path):
    env = call(tmp_path)
    assert env["contract"] == "bond.roof_model/0.2"
    assert set(env) == ENVELOPE_KEYS
    assert env["totals"]["area_sqft"] > 0 and env["totals"]["facets"] > 0
    assert (tmp_path / "cache").is_dir()


def test_stage_order(tmp_path):
    seen = []
    call(tmp_path, on_stage=seen.append)
    assert seen == ["model", "render"]
    assert set(seen) <= set(STAGES)
    idx = [STAGES.index(s) for s in seen]
    assert idx == sorted(idx)


def test_temp_work_dir_is_removed(tmp_path, monkeypatch):
    made = []
    real = tempfile.mkdtemp

    def spy(*a, **k):
        made.append(real(*a, **k))
        return made[-1]
    monkeypatch.setattr(tempfile, "mkdtemp", spy)
    call(tmp_path)
    assert len(made) == 1 and not Path(made[0]).exists()


def test_given_work_dir_is_kept_with_the_outputs(tmp_path):
    work = tmp_path / "work"
    call(tmp_path, work_dir=work)
    names = sorted(p.name for p in work.iterdir())
    assert any(n.endswith("_model.json") for n in names) and any(n.endswith("_blocks.json") for n in names)
    assert not any(n.endswith(".png") for n in names)  # render is skipped by the facade


@pytest.mark.parametrize("exc,code,retryable", [
    (GeocodeError("no match"), "address_not_found", False),
    (FootprintError("none"), "no_footprint", False),
    (AmbiguousBuilding("two"), "ambiguous_building", False),
    (LidarError("none"), "no_lidar_coverage", False),
    (LidarTooSparse("proj", 2020, 1.0, 8.0), "lidar_too_sparse", False),
    (BlocksError("bad"), "measurement_failed", False),
    (GeocodeUnavailable("down"), "upstream_unavailable", True),
    (requests.ConnectionError("down"), "upstream_unavailable", True),
    (DeadlineExceeded("late"), "timeout", True),
])
def test_every_reachable_code(tmp_path, monkeypatch, exc, code, retryable):
    def fake(*a, **k):
        raise exc
    monkeypatch.setattr("roof_measure.pipeline.run_pipeline", fake)
    with pytest.raises(MeasureError) as e:
        call(tmp_path)
    err = e.value
    assert err.code == code and err.retryable is retryable
    assert str(err).startswith(f"{code}: ") and err.__cause__ is exc
    assert set(err.to_dict()) == {"code", "message", "retryable"}
    assert err.to_dict()["code"] in errors.JOB_CODES


def test_interrupted_is_a_job_code_no_exception_maps_to():
    assert "interrupted" in errors.JOB_CODES
    for exc in (GeocodeError("x"), FootprintError("x"), AmbiguousBuilding("x"), LidarError("x"), LidarTooSparse("proj", 2020, 1.0, 8.0),
                BlocksError("x"), GeocodeUnavailable("x"), DeadlineExceeded("x"), RuntimeError("x"), ValueError("x")):
        assert errors.code_for(exc) != "interrupted"


def test_measure_error_shape():
    e = MeasureError("timeout")
    assert e.message == errors.MESSAGES["timeout"] and e.retryable is True
    assert MeasureError.from_error(e.to_dict()).to_dict() == e.to_dict()
    assert "timeout" in repr(e)


@pytest.mark.parametrize("kw", [
    {"method": "nope"}, {"lat": 34.0}, {"lng": -118.0}, {"lat": 91.0, "lng": 0.0}, {"lat": float("nan"), "lng": 0.0},
    {"deadline_s": 0}, {"deadline_s": float("inf")}, {"blocks_path": "/no/such/file.json"},
    {"solar_fixture": "/no/such/file.json"},
])
def test_bad_arguments_are_value_errors(tmp_path, kw):
    with pytest.raises(ValueError) as e:
        call(tmp_path, **kw)
    assert not isinstance(e.value, MeasureError)


def test_blank_address_needs_coordinates(tmp_path):
    with pytest.raises(ValueError):
        measure("  ", cache_dir=tmp_path, blocks_path=BLOCKS, isolate=False)
    env = measure("", lat=34.0, lng=-118.0, cache_dir=tmp_path / "c", method="lidar_skeleton", verify=False,
                  blocks_path=BLOCKS, isolate=False)
    assert env["contract"] == "bond.roof_model/0.2"


@pytest.mark.parametrize("kw", [
    {"deadline_s": True}, {"lat": "1", "lng": 1.0}, {"lat": True, "lng": 0.0}, {"lat": 1.0, "lng": False},
    {"address": 5}, {"overpass_urls": "https://x.example/api"},
])
def test_more_bad_arguments_are_value_errors(tmp_path, kw):
    args = {"cache_dir": tmp_path / "c", "blocks_path": BLOCKS, "isolate": False, "verify": False,
            "method": "lidar_skeleton", "address": ADDR} | kw
    with pytest.raises(ValueError) as e:
        measure(args.pop("address"), **args)
    assert not isinstance(e.value, (MeasureError, TypeError))


def test_a_none_address_with_coordinates_is_a_blank_address(tmp_path):
    env = measure(None, lat=34.0, lng=-118.0, cache_dir=tmp_path / "c", method="lidar_skeleton",  # type: ignore[arg-type]
                  verify=False, blocks_path=BLOCKS, isolate=False)
    assert env["contract"] == "bond.roof_model/0.2"


def test_cache_dir_is_required():
    with pytest.raises(TypeError):
        measure(ADDR)  # type: ignore[call-arg]


def test_force_is_reset_after_success_and_failure(tmp_path, monkeypatch):
    seen = []

    def fake(*a, **k):
        seen.append(cache._FORCE.get())
        raise FootprintError("none")
    call(tmp_path, force=True)
    assert cache._FORCE.get() is False
    monkeypatch.setattr("roof_measure.pipeline.run_pipeline", fake)
    with pytest.raises(MeasureError):
        call(tmp_path, force=True)
    assert seen == [True] and cache._FORCE.get() is False


def test_the_callers_force_flag_survives_a_call(tmp_path):
    cache.force_refresh(True)
    try:
        call(tmp_path, force=False)
        assert cache._FORCE.get() is True
    finally:
        cache.force_refresh(False)


def test_non_finite_numbers_in_the_envelope_fail_in_process(tmp_path, monkeypatch):
    monkeypatch.setattr("roof_measure.pipeline.run_pipeline",
                        lambda *a, **k: SimpleNamespace(envelope={"x": float("nan")}))
    with pytest.raises(MeasureError) as e:
        call(tmp_path)
    assert e.value.code == "measurement_failed" and "non-finite" in e.value.message


def test_a_temp_work_dir_is_removed_after_a_failed_call(tmp_path, monkeypatch):
    made, real = [], tempfile.mkdtemp
    monkeypatch.setattr(tempfile, "mkdtemp", lambda *a, **k: made.append(real(*a, **k)) or made[-1])

    def fake(*a, **k):
        raise FootprintError("none")
    monkeypatch.setattr("roof_measure.pipeline.run_pipeline", fake)
    with pytest.raises(MeasureError):
        call(tmp_path)
    assert len(made) == 1 and not Path(made[0]).exists()


def _auto_pipeline(monkeypatch):
    from roof_measure import pipeline

    seen = []

    def fake(address, out_dir, method, **kw):
        seen.append(method)
        if len(seen) == 1:
            raise LidarError("none")
        return SimpleNamespace(envelope={"ok": True})
    monkeypatch.setattr(pipeline, "_run", fake)
    return seen


def test_auto_falls_back_to_solar_when_both_argument_keys_are_given(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    seen = _auto_pipeline(monkeypatch)
    env = call(tmp_path, method="auto", blocks_path=None, lat=34.0, lng=-118.0, anthropic_api_key="a",
               google_solar_api_key="g")
    assert env == {"ok": True} and seen == ["lidar_skeleton", "solar_agent"]


def test_auto_does_not_fall_back_without_the_argument_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-a")
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "env-g")  # the environment must not enable the paid fallback
    seen = _auto_pipeline(monkeypatch)
    with pytest.raises(MeasureError) as e:
        call(tmp_path, method="auto", blocks_path=None, lat=34.0, lng=-118.0)
    assert e.value.code == "no_lidar_coverage" and seen == ["lidar_skeleton"]


def test_source_unreachable_reaches_the_envelope(tmp_path, monkeypatch, net):
    from shapely.geometry import box

    from roof_measure import blocks, footprint, footprint_osm, lidar
    from roof_measure.footprint_types import Footprint

    lat, lng, d = 34.0, -118.0, 0.0001
    net.routes["LACounty_Parcel"] = requests.ConnectionError("county down")
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = requests.ConnectionError("down")
    hull = Footprint(provider="lidar_hull", id="lidar_hull", polygon_wgs84=box(lng, lat, lng + d, lat + d),
                     height_ft=20.0, area_sqft=1000.0, parcel_id=None, source="lidar_hull")
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: hull)
    monkeypatch.setattr(lidar, "fetch_for_footprint", lambda *a, **k: None)
    monkeypatch.setattr(blocks, "segment_blocks",
                        lambda *a, **k: SimpleNamespace(to_json=lambda path: shutil.copy(BLOCKS, path)))
    env = call(tmp_path, blocks_path=None, lat=lat, lng=lng)
    assert "source_unreachable" in env["warning_codes"]


def test_the_library_path_needs_neither_matplotlib_nor_fastapi(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "fastapi", None)
    assert call(tmp_path)["contract"] == "bond.roof_model/0.2"


def test_callback_error_propagates(tmp_path):
    class Stop(Exception):
        pass

    def cb(name):
        raise Stop(name)
    with pytest.raises(Stop):
        call(tmp_path, on_stage=cb)


def test_env_key_is_never_used_when_the_argument_is_none(tmp_path, monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")
    constructed = []
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: constructed.append((a, k)))
    env = call(tmp_path, verify=True)
    assert constructed == []
    assert env["verification"]["verdict"] == "unverified"
    assert any("no ANTHROPIC_API_KEY" in n for n in env["verification"]["notes"])


def test_the_argument_key_builds_the_client(tmp_path, monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    constructed = []

    def fake(*a, **k):
        constructed.append(k.get("api_key"))
        raise RuntimeError("stop here")
    monkeypatch.setattr(anthropic, "Anthropic", fake)
    call(tmp_path, verify=True, anthropic_api_key="arg-key")
    assert constructed == ["arg-key"]


def test_purge_cache(tmp_path):
    d = tmp_path / "cache"
    d.mkdir()
    old, stale, fresh = d / "a.bin", d / "b.tmp", d / "c.bin"
    for f in (old, stale, fresh):
        f.write_bytes(b"x")
    past = time.time() - 40 * 86400
    os.utime(old, (past, past))
    os.utime(stale, (past, past))
    assert purge_cache(d, days=30) == 2
    assert not old.exists() and not stale.exists() and fresh.exists()


@pytest.mark.parametrize("which", ["work_dir", "cache_dir"])
def test_a_directory_argument_that_is_a_file_is_a_value_error(tmp_path, which):
    f = tmp_path / "afile"
    f.write_text("x")
    kw = {"cache_dir": tmp_path / "c", "work_dir": tmp_path / "w"} | {which: f}
    with pytest.raises(ValueError, match="must be a directory"):
        measure(ADDR, method="lidar_skeleton", verify=False, blocks_path=BLOCKS, isolate=False, **kw)
