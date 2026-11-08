"""API: fixture endpoints, the fixture method and CORS (no pipeline run, no network)."""

from fastapi.testclient import TestClient
from sites import PLACEHOLDER

from roof_measure.api import app

client = TestClient(app)


def test_fixtures_list_and_get():
    r = client.get("/fixtures")
    assert r.status_code == 200
    names = {f["name"] for f in r.json()}
    assert {"synthetic_hip", "site1_lidar"} <= names
    assert not {"site1_blocks", "solar_site1_fixture"} & names  # service inputs are not roof models
    assert client.get("/fixtures/synthetic_hip").json()["schema"] == "bond.roof_model/0.1"
    assert client.get("/fixtures/nope").status_code == 404
    assert client.get("/fixtures/..%2Fx").status_code in (400, 404)


def test_measure_fixture_method_and_cors():
    r = client.post("/measure", json={"address": PLACEHOLDER["line1"], "method": "fixture"},
                    headers={"Origin": "http://localhost:3003"})
    assert r.status_code == 200 and r.json()["source"]["method"] == "lidar_skeleton"
    assert r.headers["access-control-allow-origin"] == "http://localhost:3003"
    bad = client.post("/measure", json={"address": "x", "method": "bogus"})
    assert bad.status_code == 400


def test_measure_runs_pipeline_from_blocks_fixture_name(monkeypatch, tmp_path):
    from roof_measure import api

    monkeypatch.setattr(api, "OUT_DIR", tmp_path)  # a stale api_* cache must not mask the pipeline
    body = {"address": f"{PLACEHOLDER['line1']} API test", "method": "lidar_skeleton", "blocks_fixture": "site1_blocks.json"}
    r = client.post("/measure", json=body)
    assert r.status_code == 200 and r.json()["totals"]["total_area_sqft"] > 5000
    assert any(p.name.endswith("_model.json") for p in tmp_path.iterdir())  # the pipeline really ran
    assert any(p.name.startswith("api_") for p in tmp_path.iterdir())


def test_fixture_names_are_confined_to_the_fixtures_dir(monkeypatch, tmp_path):
    from roof_measure import api

    monkeypatch.setattr(api, "OUT_DIR", tmp_path)
    for bad in ("/etc/passwd", "../x.json", "a/b.json", "site1_blocks", "nope.json"):
        r = client.post("/measure", json={"address": "x", "blocks_fixture": bad})
        assert r.status_code == 400, bad
    r = client.post("/measure", json={"address": "x", "method": "solar_agent", "solar_fixture": "../../etc/hosts"})
    assert r.status_code == 400


def test_address_length_is_capped_and_errors_are_not_echoed(monkeypatch, tmp_path):
    from roof_measure import api

    monkeypatch.setattr(api, "OUT_DIR", tmp_path)
    assert client.post("/measure", json={"address": "x" * 201}).status_code == 422

    def boom(*a, **k):
        raise RuntimeError("secret upstream detail /private/path")

    monkeypatch.setattr(api, "run_pipeline", boom)
    r = client.post("/measure", json={"address": PLACEHOLDER["line1"]})
    assert r.status_code == 502 and "secret" not in r.text
