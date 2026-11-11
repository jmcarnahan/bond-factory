"""The real job runner end to end: blocks fixture through the pipeline, result cache, aliases, per-job dirs."""

import json
import time
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from roof_measure import api, geocode, pipeline
from roof_measure.settings import Settings

TOKEN = "t" * 32
HDR = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path / "cache"))
    app = api.create_app(Settings(data_dir=tmp_path, debug=True), token=TOKEN)
    with TestClient(app, headers=HDR) as c:
        yield c


def wait(c, job_id, want=("done", "failed")):
    end = time.time() + 20
    while time.time() < end:
        r = c.get(f"/v1/measurements/{job_id}").json()
        if r["status"] in want:
            return r
        time.sleep(0.05)
    raise AssertionError(r)


def test_blocks_fixture_runs_the_real_pipeline_then_caches(client, tmp_path):
    body = {"address": "100 Example Ave, Sampletown, CA 90000", "method": "lidar_skeleton",
            "blocks_fixture": "site1_blocks.json"}
    first = client.post("/v1/measurements", json=body, headers={"Origin": "http://localhost:3003"})
    assert first.status_code == 202 and first.json()["status"] == "queued"
    assert first.headers["access-control-allow-origin"] == "http://localhost:3003"
    done = wait(client, first.json()["id"])
    env = done["result"]
    assert env["contract"] == "bond.roof_model/0.2" and env["method_used"] == "lidar_skeleton"
    assert env["totals"]["area_sqft"] > 5000 and env["model"]["schema"] == "bond.roof_model/0.1"
    assert env["verification"]["verdict"] == "unverified" and env["verification"]["model"] is None
    assert "verifier_unverified" in env["warning_codes"] and len(env["warnings"]) == len(env["warning_codes"])
    files = {p.name.rsplit("_", 1)[-1] for p in (tmp_path / "jobs" / first.json()["id"]).iterdir()}
    assert {"blocks.json", "model.json", "model.png", "job.json", "result.json"} <= files  # per-job dir
    again = client.post("/v1/measurements", json=body)
    assert again.status_code == 202 and again.json()["status"] == "done" and again.json()["id"] != first.json()["id"]
    assert client.get(f"/v1/measurements/{again.json()['id']}").json()["result"] == env
    forced = client.post("/v1/measurements", json={**body, "force": True}).json()
    assert forced["status"] == "queued"
    assert wait(client, forced["id"])["status"] == "done"
    skip = client.post("/v1/measurements", json={**body, "verify": False}).json()  # verify is part of the key
    assert skip["status"] == "queued"
    off = wait(client, skip["id"])["result"]["verification"]
    assert off["verdict"] == "unverified" and "not requested" in off["notes"][0]


def test_fixture_method_returns_a_saved_envelope(client):
    job = client.post("/v1/measurements", json={"address": "x", "method": "fixture",
                                                "fixture": "roof_measurement_0.2_adjusted.json"}).json()
    r = wait(client, job["id"])
    assert r["status"] == "done" and r["result"]["verification"]["verdict"] == "adjusted"
    old = client.post("/v1/measurements", json={"address": "x", "method": "fixture", "fixture": "synthetic_hip.json"}).json()
    wrapped = wait(client, old["id"])["result"]
    assert wrapped["contract"] == "bond.roof_model/0.2" and wrapped["verification"]["verdict"] == "unverified"


def stub_pipeline(monkeypatch, calls):
    from roof_measure import synth_envelopes

    env = synth_envelopes.envelopes()["roof_measurement_0.2_pass"]

    def fake(address, out_dir, method, **kw):
        calls.append({"address": address, "out_dir": out_dir, "method": method, **kw})
        return NS(envelope=env, footprint_source="osm")

    monkeypatch.setattr(pipeline, "run_pipeline", fake)
    return env


def test_address_requests_are_keyed_by_the_geocoded_address(client, monkeypatch, tmp_path):
    geos, calls = [], []
    stub_pipeline(monkeypatch, calls)

    def fake_geocode(addr):
        geos.append(addr)
        return geocode.Geocoded(34.0, -118.0, "100 EXAMPLE AVE, SAMPLETOWN, CA, 90000-0001",
                                geocode.Address("100 Example Ave", "Sampletown", "CA", "90000"))

    monkeypatch.setattr(geocode, "geocode", fake_geocode)
    a = client.post("/v1/measurements", json={"address": "100 example ave apt 2, sampletown ca"}).json()
    assert wait(client, a["id"])["status"] == "done" and len(calls) == 1
    assert calls[0]["lat_lng"] == (34.0, -118.0) and calls[0]["method"] == "auto" and calls[0]["verify"] is True
    assert calls[0]["out_dir"] == tmp_path / "jobs" / a["id"] and calls[0]["deadline"].remaining() > 100
    same = client.post("/v1/measurements", json={"address": "100 example ave apt 2, sampletown ca"}).json()
    assert same["status"] == "done"  # input alias: no geocoding, no job
    other_spelling = client.post("/v1/measurements", json={"address": "100 Example Avenue, Sampletown, CA 90000"}).json()
    assert other_spelling["status"] == "queued"  # a new spelling is geocoded, then hits the key of the match
    assert wait(client, other_spelling["id"])["status"] == "done"
    assert len(calls) == 1 and len(geos) == 2
    assert client.post("/v1/measurements", json={"address": "100 example ave apt 2, sampletown ca",
                                                 "method": "lidar_skeleton"}).json()["status"] == "queued"


def test_coordinates_skip_the_geocoder(client, monkeypatch):
    calls = []
    stub_pipeline(monkeypatch, calls)
    monkeypatch.setattr(geocode, "geocode", lambda a: (_ for _ in ()).throw(AssertionError("geocoded")))
    job = client.post("/v1/measurements", json={"address": "label only", "lat": 34.1, "lng": -118.2}).json()
    assert wait(client, job["id"])["status"] == "done" and calls[0]["lat_lng"] == (34.1, -118.2)
    tiny = 0.0000001
    near = client.post("/v1/measurements", json={"address": "other label", "lat": 34.1 + tiny, "lng": -118.2}).json()
    assert near["status"] == "done"  # same 5-decimal place, same key


def test_pipeline_errors_become_codes_and_never_leak_text(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret upstream detail /private/path")

    monkeypatch.setattr(pipeline, "run_pipeline", boom)
    job = client.post("/v1/measurements", json={"address": "x", "lat": 1.0, "lng": 2.0}).json()
    r = wait(client, job["id"])
    assert r["status"] == "failed" and r["error"]["code"] == "measurement_failed" and "secret" not in json.dumps(r)
    assert not list((client.app.state.service.results.root).glob("*.json"))  # failures are not cached


def test_geocode_failure_is_address_not_found(client, monkeypatch):
    def nope(addr):
        raise geocode.GeocodeError("The Census geocoder found no match for 'x'.")

    monkeypatch.setattr(geocode, "geocode", nope)
    job = client.post("/v1/measurements", json={"address": "nowhere"}).json()
    r = wait(client, job["id"])
    assert r["error"] == {"code": "address_not_found", "retryable": False,
                          "message": "The Census geocoder found no match for 'x'."}  # pipeline messages are kept


def test_job_deadline_exceeded_is_a_timeout(tmp_path, monkeypatch):
    from roof_measure.deadline import DeadlineExceeded

    def slow(*a, **k):
        raise DeadlineExceeded("lidar")

    monkeypatch.setattr(pipeline, "run_pipeline", slow)
    app = api.create_app(Settings(data_dir=tmp_path, job_timeout_s=5), token=TOKEN)
    with TestClient(app, headers=HDR) as c:
        job = c.post("/v1/measurements", json={"address": "x", "lat": 1.0, "lng": 2.0}).json()
        r = wait(c, job["id"])
        assert r["error"]["code"] == "timeout" and r["error"]["retryable"] is True
