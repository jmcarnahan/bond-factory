import pytest

from bond_auth_py import (
    AuthRefused,
    AuthSettings,
    ClaimListPolicy,
    Claims,
    RolePolicy,
    assert_startup_safe,
    firebase_runtime_config,
    has,
    has_any,
    mock_active,
    not_invited,
    providers_payload,
)


def claims(*caps):
    return Claims("u", "u", None, list(caps), 1.0, 2.0)


def test_claim_list_policy():
    policy = ClaimListPolicy()
    assert policy.has(claims("a", "b"), "a") and not policy.has(claims("a"), "b")
    assert policy.has(["a"], "a") and policy.has({"capabilities": ["a"]}, "a")
    assert not policy.has(None, "a") and not policy.has([], "a")
    assert ClaimListPolicy(superuser="owner").has(claims("owner"), "anything")
    assert not policy.has(claims("owner"), "anything")  # no superuser by default


def test_role_policy():
    policy = RolePolicy({"admin": {"read", "write"}, "viewer": {"read"}})
    assert policy.has("admin", "write") and policy.has(["viewer"], "read")
    assert not policy.has("viewer", "write") and not policy.has("ghost", "read")
    assert policy.has(claims("viewer", "admin"), "write")
    assert policy.has(["write"], "write")  # a held string that is itself the capability
    assert policy.capabilities_of(["admin", "viewer"]) == frozenset({"read", "write"})


def test_module_helpers():
    assert has(claims("a"), "a") and not has(claims("a"), "b")
    assert has("admin", "read", RolePolicy({"admin": {"read"}}))
    assert has_any(claims("a"), "x", "a") and not has_any(claims("a"), "x", "y")
    assert has_any(claims(), )  # no caps asked: any authenticated caller


def test_providers_unconfigured(settings):
    assert providers_payload(settings) == {
        "demo": False, "email_password": True, "google": False, "google_web_client_id": None, "apple": False,
        "mock": False, "firebase": None, "sync": {"url": None}}
    assert firebase_runtime_config(settings) is None


def test_providers_configured():
    settings = AuthSettings(
        firebase_project_id="demo-example", web_api_key="web-key", firebase_web_app_id="web-app",
        firebase_messaging_sender_id="123", firebase_ios_api_key="ios-key", firebase_ios_app_id="ios-app",
        firebase_ios_bundle_id="com.example.app", google_enabled=True, google_web_client_id="client-id",
        apple_enabled=True, demo_enabled=True)
    assert providers_payload(settings, sync_url="https://sync.example.com") == {
        "demo": True, "email_password": True, "google": True, "google_web_client_id": "client-id", "apple": True,
        "mock": False,
        "firebase": {"project_id": "demo-example", "auth_domain": "demo-example.firebaseapp.com",
                     "messaging_sender_id": "123", "web": {"api_key": "web-key", "app_id": "web-app"},
                     "ios": {"api_key": "ios-key", "app_id": "ios-app", "bundle_id": "com.example.app"}},
        "sync": {"url": "https://sync.example.com"}}


def test_providers_auth_domain_and_client_id_only_with_google():
    settings = AuthSettings(firebase_project_id="p", firebase_auth_domain="login.example.com",
                            google_web_client_id="hidden")
    payload = providers_payload(settings)
    assert payload["firebase"]["auth_domain"] == "login.example.com"
    assert payload["google"] is False and payload["google_web_client_id"] is None


def test_providers_mock_has_no_firebase_object(mock_settings):
    from dataclasses import replace

    configured = replace(mock_settings, firebase_project_id="p", demo_enabled=True)
    payload = providers_payload(configured)
    assert payload["mock"] is True and payload["firebase"] is None and payload["demo"] is True
    assert providers_payload(configured, mock=False)["firebase"]["project_id"] == "p"
    assert providers_payload(AuthSettings(), mock=True)["mock"] is True


def test_settings_repr_hides_secrets():
    text = repr(AuthSettings(jwt_secret="s3cret", service_account_json="{sa}", web_api_key="k3y"))
    assert "s3cret" not in text and "{sa}" not in text and "k3y" not in text


def test_from_env(monkeypatch):
    env = {"BOND_AUTH_JWT_SECRET": "s", "BOND_AUTH_MOCK": "true", "BOND_AUTH_TEST_ENV": "1",
           "BOND_AUTH_ISSUER": "iss", "BOND_AUTH_ACCESS_TTL_MINUTES": "30", "BOND_AUTH_GOOGLE": "yes",
           "BOND_AUTH_EMAIL_PASSWORD": "false", "FIREBASE_PROJECT_ID": "p", "FIREBASE_WEB_API_KEY": "k",
           "FIREBASE_SERVICE_ACCOUNT_FILE": "/x.json", "FIREBASE_IOS_BUNDLE_ID": "b"}
    got = AuthSettings.from_env(env=env, app_name="shop")
    assert (got.jwt_secret, got.tier, got.test_env, got.issuer, got.audience) == ("s", "mock", True, "iss", "bond-api")
    assert (got.access_ttl_minutes, got.google_enabled, got.email_password_enabled) == (30, True, False)
    assert (got.firebase_project_id, got.web_api_key, got.service_account_file) == ("p", "k", "/x.json")
    assert got.firebase_ios_bundle_id == "b" and got.app_name == "shop"
    legacy = AuthSettings.from_env(env={"JWT_SECRET_KEY": "j", "ACCESS_TOKEN_EXPIRE_MINUTES": "5"})
    assert (legacy.jwt_secret, legacy.access_ttl_minutes, legacy.tier, legacy.email_password_enabled) == (
        "j", 5, "firebase", True)
    custom = AuthSettings.from_env(prefix="X_", firebase_prefix="FB_", env={"X_MOCK": "1", "FB_PROJECT_ID": "q"})
    assert custom.tier == "mock" and custom.firebase_project_id == "q"


def test_from_env_reads_the_process_environment(monkeypatch):
    monkeypatch.setenv("BOND_AUTH_AUDIENCE", "aud")
    assert AuthSettings.from_env().audience == "aud"


def test_mock_active_and_startup_refusal(monkeypatch):
    secret = "a-secret-long-enough-for-tests-0123456789"
    mock = AuthSettings(tier="mock", jwt_secret=secret)
    assert mock_active(mock)  # pytest is running
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert not mock_active(mock)
    with pytest.raises(RuntimeError):
        assert_startup_safe(mock)
    assert_startup_safe(AuthSettings(jwt_secret=secret))  # mock not requested: fine
    assert_startup_safe(AuthSettings(tier="mock", test_env=True, jwt_secret=secret))
    assert_startup_safe(AuthSettings(tier="mock", mock_enabled_only_under_test=False, jwt_secret=secret))
    assert mock_active(AuthSettings(tier="mock", test_env=True))
    assert not mock_active(AuthSettings(tier="firebase", test_env=True))


def test_startup_refuses_an_empty_jwt_secret():
    for secret in ("", "   "):
        with pytest.raises(RuntimeError, match="JWT secret"):
            assert_startup_safe(AuthSettings(jwt_secret=secret))
    with pytest.raises(RuntimeError):
        assert_startup_safe(AuthSettings())  # the default is empty


def test_refusal_defaults_and_hints(monkeypatch):
    refused = AuthRefused("deactivated")
    assert refused.status == 403 and refused.detail() == {
        "code": "deactivated", "message": "This account is deactivated. Ask the owner."}
    assert AuthRefused("invalid_token").status == 401 and AuthRefused("firebase_not_configured").status == 501
    custom = AuthRefused("company_suspended", "Paused.", hint="billing", status=402)
    assert custom.detail() == {"code": "company_suspended", "message": "Paused.", "hint": "billing"}
    assert custom.status == 402
    assert AuthRefused("something_new").status == 403
    assert not_invited("a@example.com").detail() == {"code": "not_invited", "message": "This address was not invited."}
    from bond_auth_py import errors

    assert errors.APPLE_RELAY_SUFFIX == "@privaterelay.appleid.com"
    monkeypatch.setattr(errors, "APPLE_RELAY_SUFFIX", "@example.org")  # keep real-looking addresses out of the repo
    relay = not_invited("abc@example.org")
    assert relay.detail()["hint"] == "apple_relay" and relay.status == 403
