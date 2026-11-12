import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from sdk_example.main import create_app

TEST_NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start with no SDK_EXAMPLE_* variables; a fixed oauth key keeps out/ untouched."""
    for name in list(os.environ):
        if name.startswith("SDK_EXAMPLE_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("BOND_OAUTH_KEY", "test-oauth-key")
    monkeypatch.setenv("SDK_EXAMPLE_PUBLIC_BASE", "http://testserver")  # one host: cookies set by the API come back


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A fake-mode app on a temp SQLite file, built from the environment alone."""
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    app = create_app()
    # The scheduling clock reads 2026-11-08 10:00 UTC, the day the task tests are written for: `overdue` is measured
    # against it (open and due_at < now), so a test does not change with the date the suite runs on. A fake-mode
    # /jobs/tick pins its own time and then releases the clock to real time.
    app.state.clock.freeze(TEST_NOW)
    return app


@pytest.fixture
def client(app):
    # A browser always sends Origin on a cookie-authenticated mutation; tests that need none build their own client.
    return TestClient(app, headers={"Origin": "http://localhost:8078"})
