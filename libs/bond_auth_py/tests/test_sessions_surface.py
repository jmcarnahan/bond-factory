"""Settings, cookies, error codes, providers payload, the firebase extra, the schema contract and the boundaries."""

import re
import sys
from pathlib import Path

import pytest
from sessions_support import AuthSession, Base, settings_with
from sqlalchemy import Column, String, create_engine, inspect
from sqlalchemy.orm import declarative_base

import bond_auth_py
from bond_auth_py import (
    AuthNotConfigured,
    AuthRefused,
    AuthSettings,
    SessionsMixin,
    providers_payload,
    refresh_cookie_name,
    refresh_cookie_params,
    session_cookie_params,
    verify_id_token,
)
from bond_auth_py.errors import REFUSALS

PKG = Path(bond_auth_py.__file__).parent


def test_session_defaults():
    s = AuthSettings()
    assert (s.session_access_ttl_minutes, s.refresh_ttl_days, s.refresh_max_days) == (60, 90, None)
    assert (s.refresh_reuse_grace_seconds, s.refresh_retry_seconds) == (20, 600)
    assert (s.refresh_max_sessions_per_user, s.refresh_probe_hours, s.refresh_cookie_path) == (10, 0, "/auth")
    assert s.access_ttl_minutes == 10080  # unchanged for apps without sessions


def test_session_settings_from_env():
    env = {"BOND_AUTH_SESSION_ACCESS_TTL_MINUTES": "30", "BOND_AUTH_REFRESH_TTL_DAYS": "14",
           "BOND_AUTH_REFRESH_MAX_DAYS": "90", "BOND_AUTH_REFRESH_REUSE_GRACE_SECONDS": "5",
           "BOND_AUTH_REFRESH_RETRY_SECONDS": "120", "BOND_AUTH_REFRESH_MAX_SESSIONS_PER_USER": "3",
           "BOND_AUTH_REFRESH_PROBE_HOURS": "12", "BOND_AUTH_REFRESH_COOKIE_PATH": "/api/auth"}
    s = AuthSettings.from_env(env=env)
    assert (s.session_access_ttl_minutes, s.refresh_ttl_days, s.refresh_max_days) == (30, 14, 90)
    assert (s.refresh_reuse_grace_seconds, s.refresh_retry_seconds, s.refresh_max_sessions_per_user) == (5, 120, 3)
    assert (s.refresh_probe_hours, s.refresh_cookie_path) == (12, "/api/auth")
    assert AuthSettings.from_env(env={}).refresh_ttl_days == 90
    for raw in ("0", ""):
        assert AuthSettings.from_env(env={"BOND_AUTH_REFRESH_MAX_DAYS": raw}).refresh_max_days is None
    assert AuthSettings.from_env(env={}).refresh_max_days is None


def test_refresh_cookie_params_and_name():
    params = refresh_cookie_params(AuthSettings(), True)
    assert params == {"httponly": True, "secure": True, "samesite": "lax", "path": "/auth", "max_age": 90 * 86400}
    assert refresh_cookie_params(settings_with(refresh_cookie_path="/x"), secure=False)["path"] == "/x"
    assert refresh_cookie_name("app") == "app_refresh_token"
    assert session_cookie_params(settings_with(), secure=True)["max_age"] == 10080 * 60  # unchanged
    assert session_cookie_params(settings_with(), secure=True, ttl_minutes=60)["max_age"] == 3600


EXPECTED = {
    "tenant_mismatch": 403, "consent_declined": 403, "account_mismatch": 403, "invalid_origin": 403,
    "company_suspended": 403, "provider_not_allowed": 403, "invalid_handoff": 401, "refresh_reused": 401,
    "refresh_expired": 401, "refresh_revoked": 401, "invalid_request": 400, "invalid_state": 400,
    "invalid_code": 400, "invalid_id_token": 400, "signin_expired": 400, "unknown_provider": 404,
    "provider_error": 502,
}


@pytest.mark.parametrize(("code", "status"), sorted(EXPECTED.items()))
def test_signin_codes_are_in_the_refusals_table(code, status):
    assert REFUSALS[code][0] == status and REFUSALS[code][1].strip().endswith(".")
    exc = AuthRefused(code)
    assert exc.status == status and exc.detail()["code"] == code


def test_refresh_errors_are_auth_refused_with_a_code():
    for cls, code in ((bond_auth_py.ReuseDetected, "refresh_reused"), (bond_auth_py.RefreshExpired, "refresh_expired"),
                      (bond_auth_py.RefreshRevoked, "refresh_revoked")):
        exc = cls()
        assert isinstance(exc, AuthRefused) and exc.code == code and exc.status == 401
    assert bond_auth_py.REFRESH_REUSED == "refresh_reused" and bond_auth_py.INVALID_ORIGIN == "invalid_origin"


def test_providers_payload_keeps_old_keys_and_adds_the_new_ones():
    base = providers_payload(AuthSettings(), mock=True)
    assert not {"signin", "break_glass", "default_flow"} & set(base)  # defaults leave the old payload as it was
    assert {"demo", "email_password", "google", "google_web_client_id", "apple", "mock", "firebase", "sync"} <= set(base)
    full = providers_payload(AuthSettings(), mock=True, break_glass=True, default_flow="signin",
                             signin=[{"id": "google", "label": "Google", "client_id": "secret-ish", "x": 1}])
    assert full["signin"] == [{"id": "google", "label": "Google"}]
    assert full["break_glass"] is True and full["default_flow"] == "signin"


def test_firebase_extra_missing_raises_not_configured(monkeypatch):
    monkeypatch.setitem(sys.modules, "firebase_admin", None)  # an import of it now raises ImportError
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", None)
    settings = AuthSettings(jwt_secret="x" * 40, firebase_project_id="demo-project")
    with pytest.raises(AuthNotConfigured) as err:
        verify_id_token("some-token", settings)
    assert "install bond_auth_py[firebase]" in str(err.value)
    assert isinstance(err.value, bond_auth_py.AuthUnavailable)  # routes answer 501 firebase_not_configured


def test_firebase_extra_missing_for_the_admin_and_the_startup_check(monkeypatch):
    monkeypatch.setitem(sys.modules, "firebase_admin", None)
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", None)
    settings = AuthSettings(jwt_secret="x" * 40, firebase_project_id="p", service_account_json=(
        '{"type": "service_account", "project_id": "p", "private_key": "k", "client_email": "a@b.c"}'))
    with pytest.raises(AuthNotConfigured, match=r"bond_auth_py\[firebase\]"):
        bond_auth_py.FirebaseIdentityAdmin(settings).get_user(email="a@example.com")
    with pytest.raises(AuthNotConfigured, match=r"bond_auth_py\[firebase\]"):
        bond_auth_py.check_service_account(settings)


def test_importing_the_package_never_imports_firebase_admin():
    import subprocess

    code = "import sys, bond_auth_py; sys.exit(1 if 'firebase_admin' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


def test_the_mixin_creates_the_planned_table_on_sqlite():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("auth_sessions")}
    required = {"id", "family_id", "user_id", "token_hash", "provider", "auth_time", "family_expires_at",
                "expires_at", "created_at"}
    optional = {"parent_id", "last_used_at", "rotated_at", "revoked_at", "revoke_reason", "device_label",
                "rotation_id", "last_probed_at"}
    optional.add("family_expires_at")  # NULL = no absolute cap
    required.discard("family_expires_at")
    assert set(cols) == required | optional
    assert all(not cols[n]["nullable"] for n in required if n != "id") and all(cols[n]["nullable"] for n in optional)
    indexes = {i["name"]: (i["column_names"], bool(i["unique"])) for i in insp.get_indexes("auth_sessions")}
    assert indexes == {
        "uq_auth_sessions_token_hash": (["token_hash"], True),
        "ix_auth_sessions_family_id": (["family_id"], False),
        "ix_auth_sessions_user_revoked": (["user_id", "revoked_at"], False),
        "ix_auth_sessions_expires_at": (["expires_at"], False),
    }
    keyed = declarative_base()
    type("User", (keyed,), {"__tablename__": "users", "id": Column(String, primary_key=True)})
    type("Keyed", (SessionsMixin, keyed), {})
    fks = keyed.metadata.tables["auth_sessions"].c.user_id.foreign_keys
    assert [fk.target_fullname for fk in fks] == ["users.id"]


def test_the_sessions_code_imports_no_flutter_no_framework_and_no_sibling_lib():
    pattern = re.compile(r"^\s*(?:from|import)\s+(bond_(?!auth_py\b)\w+|fastapi|starlette|flutter)\b", re.MULTILINE)
    offenders = [p.name for p in PKG.glob("*.py") if pattern.search(p.read_text())]
    assert offenders == []
    assert AuthSession.__table__.name == "auth_sessions"


def test_issued_session_repr_carries_no_token():
    from bond_auth_py import IssuedSession

    issued = IssuedSession(access_jwt="jwt-secret-value", refresh_token="refresh-secret-value", family_id="f1",
                           expires_in=3600, user_id="u1")
    text = repr(issued)
    assert "secret-value" not in text and "f1" in text
