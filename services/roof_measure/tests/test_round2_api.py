"""Review round: strict validation, body limits, 500 shape, coalescing, watchdog, malformed records, tokens."""

import json
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient
from test_jobs_api import ENVELOPE, Runs, wait

from roof_measure import api, auth
from roof_measure.jobs import JobRunner, JobStore
from roof_measure.settings import Settings

TOKEN = "t" * 32
BODY = {"address": "100 Example Ave, Sampletown, CA 90000", "lat": 1.5, "lng": 2.5}


def make(tmp_path, run, **kw):
    debug = kw.pop("debug", True)
    grace = kw.pop("grace", None)
    app = api.create_app(Settings(data_dir=tmp_path, debug=debug, **kw), token=TOKEN, run=run)
    if grace is not None:
        app.state.service.runner.grace_s = grace
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}, raise_server_exceptions=False)


@pytest.mark.parametrize("body", [
    {"address": "x", "lat": "34", "lng": 1.0}, {"address": "x", "lat": True, "lng": 1.0},
    {"address": "x", "verify": "yes"}, {"address": "x", "verify": 1}, {"address": "x", "force": "true"},
    {"address": "   "}, {"address": "\t\n"},
])
def test_strict_types_and_blank_addresses_are_422(tmp_path, body):
    r = make(tmp_path, Runs()).post("/v1/measurements", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_ints_are_fine_for_coordinates_and_the_address_is_stripped(tmp_path):
    c = make(tmp_path, Runs())
    r = c.post("/v1/measurements", json={"address": "  x  ", "lat": 34, "lng": -118})
    assert r.status_code == 202
    assert c.app.state.service.store.get(r.json()["id"])["request"]["address"] == "x"


def test_a_huge_content_length_is_refused_before_reading(tmp_path):
    c = make(tmp_path, Runs())
    r = c.post("/v1/measurements", content=b"x" * 70000, headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"


def test_unexpected_errors_are_500_with_the_error_object(tmp_path, monkeypatch):
    c = make(tmp_path, Runs())
    monkeypatch.setattr(c.app.state.service, "view", lambda i: 1 / 0)
    r = c.get("/v1/measurements/" + "0" * 32)
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "measurement_failed", "message": "The service hit an unexpected error.",
                                  "retryable": False}}


def test_openapi_and_docs_exist_only_in_debug_mode(tmp_path):
    prod = make(tmp_path, Runs(), debug=False)
    assert all(prod.get(p).status_code == 404 for p in ("/docs", "/redoc", "/openapi.json"))
    assert make(tmp_path / "d", Runs()).get("/openapi.json").status_code == 200


def test_five_identical_posts_run_the_pipeline_once(tmp_path):
    run = Runs(block=True)
    c = make(tmp_path, run, workers=2, queue_max=10)
    ids = [c.post("/v1/measurements", json=BODY).json()["id"] for _ in range(5)]
    assert len(set(ids)) == 5
    wait(c, ids[0], want=("running",))
    run.gate.set()
    results = [wait(c, i) for i in ids]
    assert run.calls == 1 and all(r["status"] == "done" and r["result"] == ENVELOPE for r in results)
    again = c.post("/v1/measurements", json=BODY).json()  # leader finished: a new identical request is a new run
    wait(c, again["id"])
    assert run.calls == 2 and c.app.state.service._inflight == {}


def test_coalesced_followers_share_a_failure_and_force_does_not_coalesce(tmp_path):
    run = Runs(exc=RuntimeError("boom"), block=True)
    c = make(tmp_path, run)
    a, b = (c.post("/v1/measurements", json=BODY).json()["id"] for _ in range(2))
    f = c.post("/v1/measurements", json={**BODY, "force": True}).json()["id"]
    wait(c, a, want=("running",))
    run.gate.set()
    for i in (a, b, f):
        assert wait(c, i)["error"]["code"] == "measurement_failed"
    assert run.calls == 2  # the forced request ran on its own


def test_coalescing_does_not_use_extra_queue_slots(tmp_path):
    run = Runs(block=True)
    c = make(tmp_path, run, workers=1, queue_max=1)
    codes = [c.post("/v1/measurements", json=BODY).status_code for _ in range(6)]
    assert codes == [202] * 6
    run.gate.set()


def test_watchdog_marks_a_stuck_job_timeout_and_the_late_result_is_ignored(tmp_path):
    release = threading.Event()

    def stuck(job, out_dir, deadline, on_stage):
        release.wait(10)
        return ENVELOPE

    c = make(tmp_path, stuck, job_timeout_s=0.2, grace=0.2)
    job = c.post("/v1/measurements", json=BODY).json()
    follower = c.post("/v1/measurements", json=BODY).json()
    r = wait(c, job["id"], secs=5)
    assert r["status"] == "failed" and r["error"] == {
        "code": "timeout", "message": "The measurement took too long; retry later.", "retryable": True}
    assert wait(c, follower["id"], secs=5)["error"]["code"] == "timeout"
    release.set()
    time.sleep(0.4)
    assert c.get(f"/v1/measurements/{job['id']}").json()["status"] == "failed"  # not overwritten with done


def test_a_malformed_job_record_does_not_crash_boot(tmp_path, caplog):
    store = JobStore(tmp_path)
    for name, text in (("c" * 32, '{"id": "c"}'), ("d" * 32, '"str"'), ("e" * 32, "[1, 2]"), ("f" * 32, "{bad")):
        (store.root / name).mkdir()
        (store.root / name / "job.json").write_text(text)
    good = store.create({"address": "x"})
    with caplog.at_level(logging.WARNING):
        c = make(tmp_path, Runs())
    assert c.get(f"/v1/measurements/{good['id']}").json()["error"]["code"] == "interrupted"
    assert c.get("/v1/measurements/" + "c" * 32).status_code == 404


def test_failure_log_carries_class_and_code_but_not_the_message_or_traceback(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="roof_measure")
    c = make(tmp_path, Runs(exc=RuntimeError("secret near 100 Example Ave /private/path")))
    wait(c, c.post("/v1/measurements", json=BODY).json()["id"])
    warn = [r for r in caplog.records if r.levelno == logging.WARNING and "job failed" in r.getMessage()]
    assert warn and "RuntimeError" in warn[0].getMessage() and "measurement_failed" in warn[0].getMessage()
    assert "Example Ave" not in warn[0].getMessage() and warn[0].exc_info is None
    debug = [r for r in caplog.records if r.levelno == logging.DEBUG and "failure detail" in r.getMessage()]
    assert debug and debug[0].exc_info  # the traceback only at DEBUG


def test_nan_in_a_result_fails_the_job_instead_of_storing_it(tmp_path):
    bad = json.loads(json.dumps(ENVELOPE))
    bad["totals"]["area_sqft"] = float("nan")
    c = make(tmp_path, lambda *a: bad)
    r = wait(c, c.post("/v1/measurements", json=BODY).json()["id"])
    assert r["status"] == "failed" and r["error"]["code"] == "measurement_failed"
    assert c.get(f"/v1/measurements/{r['id']}").status_code == 200  # not a 500 on every later GET


def test_queue_max_zero_means_no_waiting_not_no_jobs(tmp_path):
    run = Runs(block=True)
    c = make(tmp_path, run, workers=1, queue_max=0)
    assert c.post("/v1/measurements", json={**BODY, "lat": 1.0}).status_code == 202
    wait(c, c.app.state.service.store.root.iterdir().__next__().name, want=("running",))
    assert c.post("/v1/measurements", json={**BODY, "lat": 2.0}).status_code == 429
    run.gate.set()


def test_tokens_must_be_ascii_and_are_stripped():
    with pytest.raises(auth.AuthConfigError, match="ASCII"):
        auth.require_token({"ROOF_MEASURE_TOKEN": "é" * 40})
    assert auth.require_token({"ROOF_MEASURE_TOKEN": "x" * 32 + "\n"}) == "x" * 32
    with pytest.raises(auth.AuthConfigError):
        auth.require_token({"ROOF_MEASURE_TOKEN": "x" * 31 + "\n"})


def test_unwritable_data_dir_names_the_railway_fix(tmp_path, caplog, monkeypatch):
    from pathlib import Path

    def deny(self, *a, **k):
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "mkdir", deny)
    with caplog.at_level(logging.ERROR), pytest.raises(PermissionError):
        JobStore(tmp_path / "vol")
    assert "RAILWAY_RUN_UID=0" in caplog.text


def test_results_are_purged_with_the_same_retention(tmp_path):
    import os

    from roof_measure.results import ResultCache

    rc = ResultCache(tmp_path)
    rc.put("a" * 64, {"x": 1})
    rc.alias_put("b" * 64, "a" * 64)
    old = time.time() - 20 * 86400
    os.utime(rc.root / ("a" * 64 + ".json"), (old, old))
    assert rc.purge(14) == 1 and rc.get("a" * 64) is None and rc.alias_get("b" * 64) == "a" * 64


def test_runner_queue_accounting_survives_release(tmp_path):
    r = JobRunner(JobStore(tmp_path), 1, 1, 5.0, lambda *a: ENVELOPE)
    r.reserve()
    r.release()
    r.reserve()
    r.release()
    assert r._queued == 0
    r.shutdown()


def test_fetch_cache_files_older_than_30_days_are_purged_at_boot(tmp_path, monkeypatch):
    import os

    from roof_measure import cache

    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path / "cache"))
    d = cache.cache_dir()
    old, new = d / "old.bin", d / "new.bin"
    old.write_bytes(b"x")
    new.write_bytes(b"y")
    ago = time.time() - 31 * 86400
    os.utime(old, (ago, ago))
    make(tmp_path, Runs())
    assert not old.exists() and new.exists()


def test_a_claimed_job_cannot_be_failed_by_the_watchdog_mid_write(tmp_path):
    """Force the interleaving: the worker has claimed completion and is writing when the watchdog's deadline passes."""
    in_write, go = threading.Event(), threading.Event()
    c = make(tmp_path, Runs(), job_timeout_s=0.05, grace=0.05)
    store = c.app.state.service.store
    real = store.write_result

    def slow_write(job_id, result):
        in_write.set()
        assert go.wait(10)
        real(job_id, result)

    store.write_result = slow_write
    job = c.post("/v1/measurements", json=BODY).json()
    assert in_write.wait(5)
    time.sleep(0.5)  # well past deadline + grace: the watchdog has scanned several times
    assert c.get(f"/v1/measurements/{job['id']}").json()["status"] != "failed"
    go.set()
    r = wait(c, job["id"])
    assert r["status"] == "done" and r["result"] == ENVELOPE


def test_a_watchdog_flagged_job_cannot_be_claimed(tmp_path):
    r = JobRunner(JobStore(tmp_path), 1, 1, 5.0, lambda *a: ENVELOPE)
    r._abandoned.add("j1")
    assert r._claim("j1") is False
    r._active["j2"] = 0.0
    assert r._claim("j2") is True and "j2" not in r._active
    r.shutdown()
