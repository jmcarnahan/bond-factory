import ast
import pathlib

import pytest

from bond_oauth import (
    GOOGLE_DEFAULT,
    MICROSOFT_BASE,
    MICROSOFT_OFFICE,
    FakeOAuth,
    OAuthError,
    ProviderError,
    pkce,
    scope_drift,
)


def test_named_sets():
    assert "https://www.googleapis.com/auth/calendar.events" in GOOGLE_DEFAULT
    assert "offline_access" in MICROSOFT_BASE and "Files.ReadWrite" in MICROSOFT_OFFICE


def test_scope_drift_missing_and_none():
    assert scope_drift("a b", ["a", "b", "c"]) == ["c"]
    assert scope_drift("a b c", ["a", "b"]) == []
    assert scope_drift(None, "x y") == ["x", "y"]


def test_scope_drift_compares_short_names_case_insensitively():
    granted = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read"
    assert scope_drift(granted, ["mail.read", "Mail.Send"]) == ["Mail.Send"]


def test_scope_drift_google_readonly_vs_events():
    granted = "https://www.googleapis.com/auth/calendar.events.readonly"
    assert scope_drift(granted, ["https://www.googleapis.com/auth/calendar.events"]) == [
        "https://www.googleapis.com/auth/calendar.events"]


def test_scope_drift_email_alias():
    assert scope_drift("https://www.googleapis.com/auth/userinfo.email", ["email"]) == []


def test_fake_consent_url_and_exchange_honours_scopes():
    fake = FakeOAuth("/c")
    url = fake.authorize_url(state="S", challenge=pkce.challenge("v1"), scopes=["a", "b"], redirect_uri="r")
    assert url == "/c?state=S"
    tokens = fake.exchange(code="mock", verifier="v1", redirect_uri="r")
    assert tokens.scope == "a b" and tokens.refresh_token and tokens.access_token


def test_fake_exchange_needs_mock_code_and_known_verifier():
    fake = FakeOAuth("/c")
    fake.authorize_url(state="S", challenge=pkce.challenge("v1"), scopes=["a"], redirect_uri="r")
    for code, verifier in (("other", "v1"), ("mock", "wrong")):
        with pytest.raises(OAuthError):
            fake.exchange(code=code, verifier=verifier, redirect_uri="r")


def test_fake_refresh_limits_to_granted_scopes_and_can_fail():
    fake = FakeOAuth("/c")
    fake.authorize_url(state="S", challenge=pkce.challenge("v"), scopes=["a", "b"], redirect_uri="r")
    refresh = fake.exchange(code="mock", verifier="v", redirect_uri="r").refresh_token
    assert fake.refresh(refresh, scopes=["a", "zzz"]).scope == "a"
    fake.fail_refresh_with("invalid_grant")
    with pytest.raises(ProviderError) as err:
        fake.refresh(refresh, scopes=[])
    assert err.value.code == "invalid_grant"


def test_fake_unknown_refresh_token_is_invalid_grant():
    with pytest.raises(ProviderError):
        FakeOAuth("/c").refresh("nope", scopes=[])


def test_boundary_imports_only_allowed_packages():
    allowed = {"httpx", "cryptography", "sqlalchemy", "bond_oauth"}
    root = pathlib.Path(__file__).resolve().parent.parent / "bond_oauth"
    stdlib = set(__import__("sys").stdlib_module_names)
    found: set[str] = set()
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    assert found - stdlib - allowed == set()
    assert not any(name.startswith("bond_") and name != "bond_oauth" for name in found)
