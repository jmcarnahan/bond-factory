"""Bearer auth: fails closed, same 401 body for missing and wrong tokens, /healthz open, start-up refusal."""

import pytest
from fastapi.testclient import TestClient

from roof_measure import api, auth
from roof_measure.settings import Settings

TOKEN = "t" * 40
BODY = {"address": "100 Example Ave, Sampletown, CA 90000", "lat": 1.0, "lng": 2.0}


def fake_run(job, out_dir, deadline, on_stage):
    return {"contract": "bond.roof_model/0.2", "fake": True}


@pytest.fixture
def client(tmp_path):
    app = api.create_app(Settings(data_dir=tmp_path), token=TOKEN, run=fake_run)
    return TestClient(app)


def test_healthz_is_open(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok" and "pipeline_version" in r.json()


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic " + TOKEN},
                                     {"Authorization": "Bearer"}, {"Authorization": TOKEN},
                                     {"Authorization": "Bearer " + TOKEN + "x"}])
def test_missing_or_wrong_token_is_401_with_one_body(client, headers):
    r = client.post("/v1/measurements", json=BODY, headers=headers)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert r.json() == {"error": {"code": "unauthorized", "message": "Missing or invalid bearer token.",
                                  "retryable": False}}
    assert client.get("/v1/measurements/" + "0" * 32, headers=headers).status_code == 401


def test_right_token_passes(client):
    r = client.post("/v1/measurements", json=BODY, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 202


def test_cors_preflight_is_not_blocked(client):
    r = client.options("/v1/measurements", headers={"Origin": "http://localhost:3003",
                                                    "Access-Control-Request-Method": "POST"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:3003"


def test_401_carries_cors_headers(client):
    r = client.post("/v1/measurements", json=BODY, headers={"Origin": "http://localhost:3003"})
    assert r.status_code == 401 and r.headers["access-control-allow-origin"] == "http://localhost:3003"


def test_refuses_to_start_without_a_long_token():
    for env in ({}, {"ROOF_MEASURE_TOKEN": "short"}, {"ROOF_MEASURE_TOKEN": "x" * 31}):
        with pytest.raises(auth.AuthConfigError):
            auth.require_token(env)
    assert auth.require_token({"ROOF_MEASURE_TOKEN": "x" * 32}) == "x" * 32


def test_auth_off_needs_a_loopback_host():
    with pytest.raises(auth.AuthConfigError):
        auth.require_token({"ROOF_MEASURE_AUTH": "off"})  # default host is "::"
    with pytest.raises(auth.AuthConfigError):
        auth.require_token({"ROOF_MEASURE_AUTH": "off", "ROOF_MEASURE_HOST": "0.0.0.0"})
    for host in ("127.0.0.1", "::1", "localhost"):
        assert auth.require_token({"ROOF_MEASURE_AUTH": "off", "ROOF_MEASURE_HOST": host}) is None


def test_module_app_refuses_to_build_without_a_token(monkeypatch):
    for name in ("ROOF_MEASURE_TOKEN", "ROOF_MEASURE_AUTH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(api, "_app", None)
    with pytest.raises(auth.AuthConfigError):
        api.__getattr__("app")


def test_auth_off_serves_without_a_token(tmp_path):
    app = api.create_app(Settings(data_dir=tmp_path), run=fake_run,
                         env={"ROOF_MEASURE_AUTH": "off", "ROOF_MEASURE_HOST": "127.0.0.1"})
    assert TestClient(app).post("/v1/measurements", json=BODY).status_code == 202
