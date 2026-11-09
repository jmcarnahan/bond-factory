from fastapi.testclient import TestClient

from sdk_example import routes
from sdk_example.main import create_app


def test_temp_route_module_is_discovered(tmp_path, monkeypatch):
    (tmp_path / "zz_probe.py").write_text(
        "def register(app):\n"
        "    @app.get('/probe')\n"
        "    def probe():\n"
        "        return {'probe': True}\n"
    )
    monkeypatch.setattr(routes, "__path__", [*routes.__path__, str(tmp_path)])
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    client = TestClient(create_app())
    assert client.get("/probe").json() == {"probe": True}
    assert client.get("/health").status_code == 200


def test_importing_main_builds_no_app():
    from sdk_example import main

    assert not hasattr(main, "app")
