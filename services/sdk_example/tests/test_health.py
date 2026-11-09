def test_health_in_fake_mode_with_no_env(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "mode": "fake"}


def test_cors_allows_demo_origin(client):
    resp = client.get("/health", headers={"Origin": "http://localhost:8078"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:8078"


def test_fake_mode_logs_a_warning(tmp_path, monkeypatch, caplog):
    from sdk_example.main import create_app

    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    with caplog.at_level("WARNING", logger="sdk_example"):
        create_app()
    assert "FAKE mode" in caplog.text
