import os

import pytest
from fastapi.testclient import TestClient

from sdk_example.main import create_app


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Start with no SDK_EXAMPLE_* variables; a fixed oauth key keeps out/ untouched."""
    for name in list(os.environ):
        if name.startswith("SDK_EXAMPLE_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("BOND_OAUTH_KEY", "test-oauth-key")


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A fake-mode app on a temp SQLite file, built from the environment alone."""
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)
