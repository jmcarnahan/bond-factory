import json
import os
import sys
import types

import pytest

from bond_auth_py import AuthSettings, default_mock, set_verifier
from bond_auth_py.firebase_app import reset_cache

SECRET = "test-secret-that-is-long-enough-for-hs256"


class FbError(Exception):
    def __init__(self, *args):
        super().__init__(*(args[:1] or ("fb",)))


def service_account(project="demo-example") -> str:
    return json.dumps({"type": "service_account", "project_id": project, "private_key": "fake-private-key",
                       "client_email": f"api@{project}.example.com"})


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("BOND_AUTH_", "FIREBASE_")):
            monkeypatch.delenv(name)
    set_verifier(None)
    default_mock().reset()
    reset_cache()
    yield
    set_verifier(None)
    default_mock().reset()
    reset_cache()


@pytest.fixture
def settings():
    return AuthSettings(jwt_secret=SECRET)


@pytest.fixture
def mock_settings():
    """Mock tier; pytest sets PYTEST_CURRENT_TEST so it is active."""
    return AuthSettings(jwt_secret=SECRET, tier="mock")


@pytest.fixture
def fake_firebase(monkeypatch):
    """A fake ``firebase_admin`` package: nothing real is imported, nothing touches the network."""
    fb = types.ModuleType("firebase_admin")
    auth = types.ModuleType("firebase_admin.auth")
    creds = types.ModuleType("firebase_admin.credentials")
    fb.apps = []
    fb.initialized = []

    def initialize_app(**kw):
        fb.initialized.append(kw)
        return object()

    class Certificate:
        def __init__(self, info):
            self.info = info

    for name in ("InvalidIdTokenError", "ExpiredIdTokenError", "RevokedIdTokenError", "UserDisabledError",
                 "UserNotFoundError", "EmailAlreadyExistsError"):
        setattr(auth, name, type(name, (FbError,), {}))
    def unstubbed(*args, **kwargs):
        raise AssertionError("this firebase_admin.auth call was not stubbed by the test")

    for name in ("verify_id_token", "create_user", "get_user", "get_user_by_email", "update_user", "delete_user",
                 "revoke_refresh_tokens", "generate_password_reset_link"):
        setattr(auth, name, unstubbed)
    fb.initialize_app = initialize_app
    fb.auth, fb.credentials = auth, creds
    creds.Certificate = Certificate
    monkeypatch.setitem(sys.modules, "firebase_admin", fb)
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", auth)
    monkeypatch.setitem(sys.modules, "firebase_admin.credentials", creds)
    return fb
