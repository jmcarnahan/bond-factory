"""Operational behaviour: log lines, admission before disk writes, retention, force vs the fetch cache, transcripts."""

import logging
import os
import time
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from test_jobs_api import ENVELOPE, Runs, wait

from roof_measure import api, cache, pipeline
from roof_measure.jobs import JobStore
from roof_measure.settings import Settings

TOKEN = "t" * 32
BODY = {"address": "100 Example Ave, Sampletown, CA 90000", "lat": 1.5, "lng": 2.5}


def app_for(tmp_path, run, **kw):
    return TestClient(api.create_app(Settings(data_dir=tmp_path, **kw), token=TOKEN, run=run),
                      headers={"Authorization": f"Bearer {TOKEN}"})


def test_info_logs_reach_the_log_stream(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="roof_measure")
    c = app_for(tmp_path, Runs())
    assert any("starting" in r.getMessage() and "bind_host=" in r.getMessage() for r in caplog.records)
    job = c.post("/v1/measurements", json=BODY).json()
    wait(c, job["id"])
    done = [r.getMessage() for r in caplog.records if "job done" in r.getMessage()]
    assert done and job["id"] in done[0] and "ms=" in done[0]
    assert "Example Ave" not in caplog.text and TOKEN not in caplog.text  # no address at INFO, never the token


def test_basicconfig_installs_a_key_value_format(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: seen.update(kw))
    app_for(tmp_path, Runs())
    assert seen["level"] == logging.INFO and "level=%(levelname)s" in seen["format"]


def test_a_refused_request_leaves_no_job_dir(tmp_path):
    run = Runs(block=True)
    c = app_for(tmp_path, run, workers=1, queue_max=1)
    a = c.post("/v1/measurements", json={**BODY, "lat": 1.0}).json()
    wait(c, a["id"], want=("running",))
    c.post("/v1/measurements", json={**BODY, "lat": 2.0})
    before = sorted(os.listdir(tmp_path / "jobs"))
    assert c.post("/v1/measurements", json={**BODY, "lat": 3.0}).status_code == 429
    assert sorted(os.listdir(tmp_path / "jobs")) == before and len(before) == 2
    run.gate.set()


def test_old_finished_job_dirs_are_purged_on_boot_and_after_each_job(tmp_path):
    store = JobStore(tmp_path)
    old, fresh, running = (store.create({"address": n}) for n in "ofr")
    store.update(old["id"], status="done")
    store.update(fresh["id"], status="done")
    old_json = store.job_dir(old["id"]) / "job.json"
    ago = time.time() - 20 * 86400
    os.utime(old_json, (ago, ago))
    store.update(running["id"], status="running")
    os.utime(store.job_dir(running["id"]) / "job.json", (ago, ago))  # old but active: kept until the boot scan
    c = app_for(tmp_path, Runs(), retention_days=14)  # boot: purge, then interrupted scan
    names = set(os.listdir(tmp_path / "jobs"))
    assert old["id"] not in names and fresh["id"] in names and running["id"] in names
    # after each job
    mid = store.create({"address": "m"})
    store.update(mid["id"], status="failed")
    os.utime(store.job_dir(mid["id"]) / "job.json", (ago, ago))
    job = c.post("/v1/measurements", json=BODY).json()
    wait(c, job["id"])
    end = time.time() + 5
    while mid["id"] in os.listdir(tmp_path / "jobs") and time.time() < end:
        time.sleep(0.05)
    assert mid["id"] not in os.listdir(tmp_path / "jobs") and job["id"] in os.listdir(tmp_path / "jobs")


def test_retention_days_comes_from_the_env(tmp_path):
    assert Settings.from_env({"DATA_DIR": str(tmp_path)}).retention_days == 14
    assert Settings.from_env({"DATA_DIR": str(tmp_path), "ROOF_MEASURE_JOB_RETENTION_DAYS": "3"}).retention_days == 3


def test_force_refreshes_the_fetch_cache_for_that_job_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOF_MEASURE_CACHE", str(tmp_path / "cache"))
    sent = []
    monkeypatch.setattr(cache, "_send", lambda m, url, params, data, headers, timeout: sent.append(url) or b"{}")

    def fake_pipeline(address, out_dir, method, **kw):
        cache.fetch_bytes("https://example.test/tile")
        return NS(envelope=ENVELOPE, footprint_source="osm")

    monkeypatch.setattr(pipeline, "run_pipeline", fake_pipeline)
    c = api.create_app(Settings(data_dir=tmp_path), token=TOKEN)
    c = TestClient(c, headers={"Authorization": f"Bearer {TOKEN}"})

    def go(**extra):
        r = c.post("/v1/measurements", json={**BODY, "lat": 1.5 + len(sent) / 1000, **extra}).json()
        assert wait(c, r["id"])["status"] == "done"

    go()
    assert len(sent) == 1
    go()  # a different place, same URL: the fetch cache answers
    assert len(sent) == 1
    go(force=True)
    assert len(sent) == 2  # force skipped the cached body
    go()
    assert len(sent) == 2  # and the flag did not leak into the next job on that worker thread


def test_verifier_transcript_is_written_per_job(tmp_path, monkeypatch):
    from conftest import FIXTURES

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = pipeline.run_pipeline("x", tmp_path, "lidar_skeleton", blocks_path=FIXTURES / "site1_blocks.json")
    path = res.paths["verifier_transcript"]
    assert path.name == "verifier_transcript.json" and path.read_text().strip() == "[]"
    res = pipeline.run_pipeline("x", tmp_path / "b", "lidar_skeleton", blocks_path=FIXTURES / "site1_blocks.json",
                                verify=False)
    assert "verifier_transcript" not in res.paths


def test_verifier_transcript_content_comes_from_the_verify_result(tmp_path, monkeypatch):
    from conftest import FIXTURES

    import roof_measure.verify as v

    real = v.verify

    def with_transcript(model, **kw):
        r = real(model, **kw)
        r.transcript = [{"round": 1, "tool": "recompute_totals"}]
        return r

    monkeypatch.setattr(v, "verify", with_transcript)
    res = pipeline.run_pipeline("x", tmp_path, "lidar_skeleton", blocks_path=FIXTURES / "site1_blocks.json")
    assert "recompute_totals" in res.paths["verifier_transcript"].read_text()


def test_only_the_solar_key_enables_solar(monkeypatch):
    from roof_measure import footprint_solar
    from roof_measure.settings import keys_present

    for n in ("GOOGLE_SOLAR_API_KEY", "GOOGLE_MAPS_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "shared")
    monkeypatch.setenv("GOOGLE_API_KEY", "shared")
    assert footprint_solar.solar_key() is None
    assert keys_present()[0] is False
    assert pipeline.SOLAR_KEY_ENV == ("GOOGLE_SOLAR_API_KEY",)
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "k")
    assert footprint_solar.solar_key() == "k" and keys_present()[0] is True


@pytest.mark.parametrize("name", ["ROOF_MEASURE_JOB_RETENTION_DAYS", "ROOF_MEASURE_FIXTURES"])
def test_env_vars_are_in_the_contract_table(name):
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[3] / "docs" / "contract-0.2.md").read_text()
    assert f"`{name}`" in doc
