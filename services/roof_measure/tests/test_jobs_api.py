"""The async job API with a fake run (no network): status flow, result cache, force, 404, 429, restart."""

import json
import threading
import time

import pytest
from conftest import FIXTURES
from fastapi.testclient import TestClient

from roof_measure import api
from roof_measure.jobs import JobStore, write_json_atomic
from roof_measure.settings import Settings

BODY = {"address": "100 Example Ave, Sampletown, CA 90000", "lat": 1.5, "lng": 2.5}
ENVELOPE = json.loads((FIXTURES / "roof_measurement_0.2_pass.json").read_text())


class Runs:
    """A scripted run: counts calls, can block until released, can raise."""

    def __init__(self, exc=None, block=False):
        self.calls, self.exc, self.gate = 0, exc, threading.Event()
        if not block:
            self.gate.set()

    def __call__(self, job, out_dir, deadline, on_stage):
        self.calls += 1
        on_stage("measure")
        assert self.gate.wait(10)
        if self.exc:
            raise self.exc
        key = job["request"]
        from roof_measure.keys import request_key
        self.last_key = request_key(key)
        return ENVELOPE


def make(tmp_path, run, **kw):
    settings = Settings(data_dir=tmp_path, debug=kw.pop("debug", True), **kw)
    app = api.create_app(settings, token="t" * 32, run=run)
    return TestClient(app, headers={"Authorization": "Bearer " + "t" * 32})


def wait(client, job_id, want=("done", "failed"), secs=10):
    end = time.time() + secs
    while time.time() < end:
        r = client.get(f"/v1/measurements/{job_id}").json()
        if r["status"] in want:
            return r
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} stuck: {r}")


def test_post_then_poll_to_done(tmp_path):
    c = make(tmp_path, Runs())
    r = c.post("/v1/measurements", json=BODY)
    assert r.status_code == 202 and r.json()["status"] == "queued"
    done = wait(c, r.json()["id"])
    assert done["status"] == "done" and done["result"]["contract"] == "bond.roof_model/0.2"
    assert "error" not in done


def test_cached_result_answers_done_at_once_and_force_bypasses(tmp_path):
    run = Runs()
    c = make(tmp_path, run)
    first = c.post("/v1/measurements", json=BODY).json()
    wait(c, first["id"])
    svc = c.app.state.service
    from roof_measure.keys import request_key
    svc.results.put(request_key({**BODY, "method": "auto", "verify": True}), ENVELOPE)  # what the runner does
    again = c.post("/v1/measurements", json=BODY)
    assert again.status_code == 202 and again.json()["status"] == "done" and again.json()["id"] != first["id"]
    assert c.get(f"/v1/measurements/{again.json()['id']}").json()["result"] == ENVELOPE
    assert run.calls == 1
    forced = c.post("/v1/measurements", json={**BODY, "force": True}).json()
    assert forced["status"] == "queued"
    wait(c, forced["id"])
    assert run.calls == 2
    other = c.post("/v1/measurements", json={**BODY, "method": "lidar_skeleton"}).json()  # method is in the key
    assert other["status"] == "queued"


def test_unknown_job_is_404_with_an_error_object(tmp_path):
    c = make(tmp_path, Runs())
    for bad in ("0" * 32, "nope", "..%2F..%2Fetc", "A" * 32):
        r = c.get(f"/v1/measurements/{bad}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_job"
        assert r.json()["error"]["retryable"] is False


def test_queue_full_is_429_with_retry_after(tmp_path):
    run = Runs(block=True)
    c = make(tmp_path, run, workers=1, queue_max=1)
    a = c.post("/v1/measurements", json={**BODY, "lat": 1.0}).json()
    wait(c, a["id"], want=("running",))
    b = c.post("/v1/measurements", json={**BODY, "lat": 2.0})
    assert b.status_code == 202 and b.json()["status"] == "queued"
    third = c.post("/v1/measurements", json={**BODY, "lat": 3.0})
    assert third.status_code == 429 and third.headers["retry-after"] == "30"
    assert third.json()["error"] == {"code": "queue_full", "message": "The service is busy; retry shortly.",
                                     "retryable": True}
    run.gate.set()
    assert wait(c, a["id"])["status"] == "done" and wait(c, b.json()["id"])["status"] == "done"
    assert c.post("/v1/measurements", json={**BODY, "lat": 4.0}).status_code == 202  # room again


def test_running_status_exposes_the_stage(tmp_path):
    run = Runs(block=True)
    c = make(tmp_path, run)
    job = c.post("/v1/measurements", json=BODY).json()
    r = wait(c, job["id"], want=("running",))
    assert r["stage"] == "measure"
    run.gate.set()
    wait(c, job["id"])


def test_restart_marks_unfinished_jobs_interrupted(tmp_path):
    store = JobStore(tmp_path)
    queued, running = store.create({"address": "x"}), store.create({"address": "y"})
    store.update(running["id"], status="running")
    finished = store.create({"address": "z"})
    store.update(finished["id"], status="done")
    store.write_result(finished["id"], ENVELOPE)
    c = make(tmp_path, Runs())  # "boot"
    for j in (queued, running):
        r = c.get(f"/v1/measurements/{j['id']}").json()
        assert r["status"] == "failed" and r["error"]["code"] == "interrupted" and r["error"]["retryable"] is True
    assert c.get(f"/v1/measurements/{finished['id']}").json()["status"] == "done"


def test_job_json_write_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "j" / "job.json"
    write_json_atomic(path, {"a": 1})
    with pytest.raises(TypeError):
        write_json_atomic(path, {"a": object()})
    assert json.loads(path.read_text()) == {"a": 1}  # the old file survives a failed write
    assert [p.name for p in path.parent.iterdir()] == ["job.json"]  # no temp file left behind
    import os
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        write_json_atomic(path, {"a": 2})
    assert json.loads(path.read_text()) == {"a": 1}


def test_failed_job_maps_the_exception_to_a_code(tmp_path):
    from roof_measure.lidar import LidarTooSparse
    c = make(tmp_path, Runs(exc=LidarTooSparse("P", 2020, 3.0, 8.0)))
    job = c.post("/v1/measurements", json=BODY).json()
    r = wait(c, job["id"])
    assert r["status"] == "failed" and r["error"]["code"] == "lidar_too_sparse" and "result" not in r
    assert r["error"]["retryable"] is False


@pytest.mark.parametrize("body", [
    {"address": ""}, {"address": "x" * 201}, {"address": "x", "lat": 91, "lng": 0}, {"address": "x", "lat": 1},
    {"address": "x", "lng": 1}, {"address": "x", "lat": 0, "lng": 181}, {"address": "x", "method": "bogus"},
    {"address": "x", "surprise": 1}, {"address": "x", "verify": "maybe"}, {}, {"address": 5},
])
def test_invalid_requests_are_422_invalid_request(tmp_path, body):
    c = make(tmp_path, Runs())
    r = c.post("/v1/measurements", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    assert "retryable" in r.json()["error"]


def test_non_json_and_oversize_bodies_are_422(tmp_path):
    c = make(tmp_path, Runs())
    assert c.post("/v1/measurements", content=b"not json").status_code == 422
    assert c.post("/v1/measurements", json={"address": "x" * 20000}).status_code == 422


def test_debug_inputs_need_debug_mode_and_stay_in_the_fixtures_dir(tmp_path):
    prod = make(tmp_path, Runs(), debug=False)
    for body in ({"address": "x", "method": "fixture"}, {"address": "x", "blocks_fixture": "site1_blocks.json"}):
        assert prod.post("/v1/measurements", json=body).status_code == 422
    assert prod.get("/fixtures").status_code == 404
    dev = make(tmp_path, Runs())
    for bad in ("/etc/passwd", "../x.json", "a/b.json", "nope.json", "nope", "..", "a b"):
        assert dev.post("/v1/measurements", json={"address": "x", "blocks_fixture": bad}).status_code == 422, bad
    assert dev.post("/v1/measurements", json={"address": "x", "blocks_fixture": "site1_blocks.json"}).status_code == 202


def test_debug_fixture_routes_list_models_and_envelopes(tmp_path):
    c = make(tmp_path, Runs())
    items = {f["name"]: f for f in c.get("/fixtures").json()}
    assert items["synthetic_hip"]["kind"] == "model" and items["roof_measurement_0.2_pass"]["kind"] == "envelope"
    assert "site1_blocks" not in items and "synthetic_solar_response" not in items
    assert c.get("/fixtures/roof_measurement_0.2_pass").json()["contract"] == "bond.roof_model/0.2"
    assert c.get("/fixtures/nope").status_code == 404 and c.get("/fixtures/..%2Fx").status_code == 404


def test_bare_fixture_names_get_json_appended_and_share_a_cache_key(tmp_path):
    c = make(tmp_path, Runs())
    a = c.post("/v1/measurements", json={"address": "x", "blocks_fixture": "site1_blocks"})
    assert a.status_code == 202
    wait(c, a.json()["id"])
    c.app.state.service.results.put(
        __import__("roof_measure.keys", fromlist=["request_key"]).request_key(
            {"address": "x", "method": "auto", "verify": True, "blocks_fixture": "site1_blocks.json"}), ENVELOPE)
    assert c.post("/v1/measurements", json={"address": "x", "blocks_fixture": "site1_blocks.json"}).json()["status"] == "done"


def test_fixtures_dir_resolution(tmp_path):
    from roof_measure.settings import Settings, resolve_fixtures_dir

    assert resolve_fixtures_dir({"ROOF_MEASURE_FIXTURES": str(tmp_path)}) == tmp_path
    assert Settings.from_env({"DATA_DIR": str(tmp_path), "ROOF_MEASURE_FIXTURES": str(tmp_path)}).fixtures_dir == tmp_path
    assert (resolve_fixtures_dir({}) / "synthetic_hip.json").is_file()  # the repo tree beside the source
