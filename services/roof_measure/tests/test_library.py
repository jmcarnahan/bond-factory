"""measure() facade, in process: fixtures only, no network, no real address."""

import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from conftest import FIXTURES
from house_helpers import house

import roof_measure
from roof_measure import cache, errors, library
from roof_measure.deadline import DeadlineExceeded
from roof_measure.footprint_types import AmbiguousBuilding, FootprintError
from roof_measure.geocode import GeocodeError, GeocodeUnavailable
from roof_measure.library import STAGES, MeasureError, measure, purge_cache
from roof_measure.lidar import LidarError, LidarTooSparse
from roof_measure.model import ModelError

ADDR = "100 Example Ave, Sampletown, CA 90000"
ENVELOPE_KEYS = set(json.loads((FIXTURES / "roof_measurement_0.2_unverified.json").read_text()))


def call(tmp_path, **kw):
    args = {"cache_dir": tmp_path / "cache", "points_path": house(tmp_path), "isolate": False}
    return measure(ADDR, **(args | kw))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(cache, "_send", boom)


def test_public_api():
    assert set(roof_measure.__all__) == {"measure", "MeasureError", "purge_cache", "STAGES", "KILL_GRACE_S"}
    assert STAGES == ("geocode", "footprint", "lidar", "model")
    assert library.KILL_GRACE_S == 30.0


def test_happy_path_on_the_synthetic_house(tmp_path):
    env = call(tmp_path)
    assert env["contract"] == "bond.roof_model/0.2"
    assert set(env) == ENVELOPE_KEYS
    assert env["totals"]["area_sqft"] > 0 and env["totals"]["plane_count"] > 0
    assert (tmp_path / "cache").is_dir()


def test_stage_order(tmp_path):
    seen = []
    call(tmp_path, on_stage=seen.append)
    assert seen == ["model"]
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
    assert any(n.endswith("_model.json") for n in names) and any(n.endswith("_engine.json") for n in names)
    assert not any(n.endswith(".png") for n in names)  # render is skipped by the facade


@pytest.mark.parametrize("exc,code,retryable", [
    (GeocodeError("no match"), "address_not_found", False),
    (FootprintError("none"), "no_footprint", False),
    (AmbiguousBuilding("two"), "ambiguous_building", False),
    (LidarError("none"), "no_lidar_coverage", False),
    (LidarTooSparse("proj", 2020, 1.0, 8.0), "lidar_too_sparse", False),
    (ModelError("bad"), "measurement_failed", False),
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


def test_measure_error_shape():
    e = MeasureError("timeout")
    assert e.message == errors.MESSAGES["timeout"] and e.retryable is True
    assert MeasureError.from_error(e.to_dict()).to_dict() == e.to_dict()
    assert "timeout" in repr(e)


@pytest.mark.parametrize("kw", [
    {"lat": 34.0}, {"lng": -118.0}, {"lat": 91.0, "lng": 0.0}, {"lat": float("nan"), "lng": 0.0},
    {"deadline_s": 0}, {"deadline_s": float("inf")}, {"points_path": "/no/such/folder"},
])
def test_bad_arguments_are_value_errors(tmp_path, kw):
    with pytest.raises(ValueError) as e:
        call(tmp_path, **kw)
    assert not isinstance(e.value, MeasureError)


def test_blank_address_needs_coordinates(tmp_path):
    with pytest.raises(ValueError):
        measure("  ", cache_dir=tmp_path, isolate=False)
    env = measure("", lat=34.0, lng=-118.0, cache_dir=tmp_path / "c",
                  points_path=house(tmp_path), isolate=False)
    assert env["contract"] == "bond.roof_model/0.2"


@pytest.mark.parametrize("kw", [
    {"deadline_s": True}, {"lat": "1", "lng": 1.0}, {"lat": True, "lng": 0.0}, {"lat": 1.0, "lng": False},
    {"address": 5}, {"overpass_urls": "https://x.example/api"},
])
def test_more_bad_arguments_are_value_errors(tmp_path, kw):
    args = {"cache_dir": tmp_path / "c", "points_path": house(tmp_path), "isolate": False,
            "address": ADDR} | kw
    with pytest.raises(ValueError) as e:
        measure(args.pop("address"), **args)
    assert not isinstance(e.value, (MeasureError, TypeError))


def test_a_none_address_with_coordinates_is_a_blank_address(tmp_path):
    env = measure(None, lat=34.0, lng=-118.0, cache_dir=tmp_path / "c",  # type: ignore[arg-type]
                  points_path=house(tmp_path), isolate=False)
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


def test_callback_error_propagates(tmp_path):
    class Stop(Exception):
        pass

    def cb(name):
        raise Stop(name)
    with pytest.raises(Stop):
        call(tmp_path, on_stage=cb)


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
        measure(ADDR, points_path=house(tmp_path), isolate=False, **kw)


def test_source_unreachable_reaches_the_envelope(tmp_path, monkeypatch, net):
    """County and OpenStreetMap down, the LiDAR hull answers: the plane engine measures it and the envelope says so."""

    from test_pipeline_engine import EPSG, ORIGIN, World  # noqa: F401  (the pipeline test's fakes)

    from roof_measure import footprint, footprint_osm, lidar
    from roof_measure.footprint_types import Footprint
    from roof_measure.frame import project_geometry

    w = World(main="gable_d8")
    lat, lng = w.point()
    net.routes["LACounty_Parcel"] = requests.ConnectionError("county down")
    for u in footprint_osm.OVERPASS_URLS:
        net.routes[u] = requests.ConnectionError("down")
    wgs = project_geometry(w.main_wall, EPSG, 4326)
    hull = Footprint(provider="lidar_hull", id="lidar_hull", polygon_wgs84=wgs, height_ft=20.0, area_sqft=1000.0,
                     parcel_id=None, source="lidar_hull")
    monkeypatch.setattr(footprint, "fetch_hull", lambda *a, **k: hull)
    monkeypatch.setattr(lidar, "fetch_for_footprint", w.lidar)
    env = call(tmp_path, points_path=None, lat=lat, lng=lng)
    assert "source_unreachable" in env["warning_codes"]
