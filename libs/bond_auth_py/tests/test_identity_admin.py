"""The identity admin without the network: credential loading, app creation, the mail request, error mapping."""

import json

import pytest
from conftest import service_account

from bond_auth_py import (
    AuthSettings,
    AuthUnavailable,
    FirebaseIdentityAdmin,
    IdentityExists,
    IdentityNotFound,
    MailNotSent,
    MockIdentities,
    MockIdentityAdmin,
    admin_ready,
    check_service_account,
)
from bond_auth_py import admin as admin_module
from bond_auth_py.firebase_app import firebase_app, service_account_info


def test_verify_only_is_not_admin_ready_and_admin_calls_refuse(fake_firebase):
    settings = AuthSettings(firebase_project_id="demo-example")
    assert admin_ready(settings) is False
    admin = FirebaseIdentityAdmin(settings)
    with pytest.raises(AuthUnavailable):
        admin.create_user("someone@example.com", "Someone")
    with pytest.raises(AuthUnavailable):
        admin.disable_user("uid")


def test_credential_order_json_text_then_file_then_project_only(tmp_path):
    path = tmp_path / "sa.json"
    path.write_text(service_account("from-file"))
    file_only = AuthSettings(service_account_file=str(path))
    assert admin_ready(file_only) and service_account_info(file_only)["project_id"] == "from-file"
    both = AuthSettings(service_account_file=str(path), service_account_json=service_account("from-json"))
    assert service_account_info(both)["project_id"] == "from-json"  # the text wins over the file
    broken = AuthSettings(service_account_file=str(path), service_account_json="{not json")
    assert service_account_info(broken)["project_id"] == "from-file"  # unusable text falls through
    missing = AuthSettings(service_account_file=str(tmp_path / "missing.json"))
    assert admin_ready(missing) is False and service_account_info(missing) is None
    path.write_text(json.dumps({"type": "authorized_user"}))  # not a service-account key
    assert admin_ready(AuthSettings(service_account_file=str(path))) is False


def test_file_is_reread_when_it_changes(tmp_path):
    path = tmp_path / "sa.json"
    path.write_text(service_account("one"))
    settings = AuthSettings(service_account_file=str(path))
    assert service_account_info(settings)["project_id"] == "one"
    path.write_text(service_account("two-two"))
    assert service_account_info(settings)["project_id"] == "two-two"


def test_check_service_account(fake_firebase):
    check_service_account(AuthSettings())  # nothing set: verify-only is fine
    check_service_account(AuthSettings(service_account_json=service_account()))
    with pytest.raises(RuntimeError) as err:
        check_service_account(AuthSettings(service_account_json="{oops fake-private-key"))
    assert "fake-private-key" not in str(err.value)
    fake_firebase.credentials.Certificate = lambda info: (_ for _ in ()).throw(ValueError("bad key"))
    with pytest.raises(RuntimeError):
        check_service_account(AuthSettings(service_account_json=service_account()))


def test_the_app_is_built_with_the_certificate_the_key_project_and_the_configured_name(fake_firebase):
    firebase_app(AuthSettings(service_account_json=service_account("from-key"), app_name="shop"))
    seen = fake_firebase.initialized[-1]
    assert isinstance(seen["credential"], fake_firebase.credentials.Certificate)
    assert seen["options"] == {"projectId": "from-key"} and seen["name"] == "shop"
    firebase_app(AuthSettings(service_account_json=service_account("from-key"), app_name="shop"))
    assert len(fake_firebase.initialized) == 1  # once per name
    firebase_app(AuthSettings(service_account_json=service_account("from-key"), firebase_project_id="explicit",
                              app_name="other"))
    assert fake_firebase.initialized[-1]["options"] == {"projectId": "explicit"}
    firebase_app(AuthSettings(firebase_project_id="explicit", app_name="verify-only"))
    assert "credential" not in fake_firebase.initialized[-1]


class Capture:
    """Replaces the HTTP post: records the call and answers with a status or raises."""

    def __init__(self, status=200, error=None):
        self.status, self.error, self.sent = status, error, {}

    def __call__(self, url, body, headers, timeout):
        self.sent = {"url": url, "body": body, "headers": headers, "timeout": timeout}
        if self.error:
            raise self.error
        return self.status


def test_set_password_mail_request_shape_and_locale(monkeypatch):
    capture = Capture()
    monkeypatch.setattr(admin_module, "_post_json", capture)
    admin = FirebaseIdentityAdmin(AuthSettings(web_api_key="web-key-123"))
    admin.send_password_reset("  Luis@example.com ", "es")
    assert capture.sent["url"] == "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key=web-key-123"
    assert capture.sent["body"] == {"requestType": "PASSWORD_RESET", "email": "luis@example.com"}
    assert capture.sent["headers"] == {"X-Firebase-Locale": "es"} and capture.sent["timeout"] == 10.0
    admin.send_password_reset("luis@example.com", "klingon")  # an unknown language falls back to English
    assert capture.sent["headers"] == {"X-Firebase-Locale": "en"}
    admin.send_password_reset("luis@example.com", "pt-BR")
    assert capture.sent["headers"] == {"X-Firebase-Locale": "pt-BR"}


def test_mail_failures_raise_mail_not_sent_without_leaking_the_key(monkeypatch, caplog):
    with pytest.raises(MailNotSent):
        FirebaseIdentityAdmin(AuthSettings()).send_password_reset("a@example.com")  # no key configured
    admin = FirebaseIdentityAdmin(AuthSettings(web_api_key="web-key-SECRET"))
    monkeypatch.setattr(admin_module, "_post_json", Capture(status=400))
    with pytest.raises(MailNotSent) as refused:
        admin.send_password_reset("a@example.com")
    monkeypatch.setattr(admin_module, "_post_json",
                        Capture(error=ConnectionError("cannot reach https://x/?key=web-key-SECRET")))
    with caplog.at_level("DEBUG"), pytest.raises(MailNotSent) as down:
        admin.send_password_reset("a@example.com")
    assert "SECRET" not in str(refused.value) and "SECRET" not in str(down.value) and "SECRET" not in caplog.text
    assert down.value.__cause__ is None  # `from None`: the URL with the key is not chained either


def test_admin_calls_map_firebase_errors_to_typed_exceptions(fake_firebase, monkeypatch):
    auth = fake_firebase.auth
    admin = FirebaseIdentityAdmin(AuthSettings(service_account_json=service_account()))

    def exists(**kw):
        raise auth.EmailAlreadyExistsError("exists")

    monkeypatch.setattr(auth, "create_user", exists)
    with pytest.raises(IdentityExists):
        admin.create_user("a@example.com", "A")

    def missing(*a, **kw):
        raise auth.UserNotFoundError("none")

    monkeypatch.setattr(auth, "get_user_by_email", missing)
    monkeypatch.setattr(auth, "get_user", missing)
    assert admin.get_user(email="a@example.com") is None and admin.get_user(uid="u") is None

    for name in ("update_user", "delete_user", "revoke_refresh_tokens"):
        monkeypatch.setattr(auth, name, missing)
    for call in (admin.disable_user, admin.revoke_sessions, admin.delete_user):
        with pytest.raises(IdentityNotFound):
            call("uid")
    with pytest.raises(IdentityNotFound):
        admin.set_password("uid", "pw")

    def broken(*a, **kw):
        raise RuntimeError("quota exceeded for a@example.com")

    monkeypatch.setattr(auth, "generate_password_reset_link", broken)
    with pytest.raises(AuthUnavailable) as err:
        admin.password_reset_link("a@example.com")
    assert "a@example.com" not in str(err.value)  # the message names the step, never the data
    monkeypatch.setattr(auth, "generate_password_reset_link", lambda email, app=None: "https://example.com/reset")
    assert admin.password_reset_link("A@example.com") == "https://example.com/reset"


def test_get_user_shape_and_update_calls(fake_firebase, monkeypatch):
    import types

    auth = fake_firebase.auth
    admin = FirebaseIdentityAdmin(AuthSettings(service_account_json=service_account()))
    user = types.SimpleNamespace(uid="u9", email="A@example.com", disabled=False,
                                 provider_data=[types.SimpleNamespace(provider_id="google.com")],
                                 user_metadata=types.SimpleNamespace(creation_timestamp=1_900_000_000_000))
    monkeypatch.setattr(auth, "get_user", lambda uid, app=None: user)
    got = admin.get_user(uid="u9")
    assert got["uid"] == "u9" and got["email"] == "a@example.com" and got["providers"] == ["google.com"]
    assert got["created_at"].year == 2030 and got["created_at"].tzinfo is None
    updates = []
    monkeypatch.setattr(auth, "update_user", lambda uid, app=None, **f: updates.append((uid, f)))
    admin.disable_user("u9")
    admin.disable_user("u9", False)
    admin.update_email("u9", " New@example.com ")
    assert updates == [("u9", {"disabled": True}), ("u9", {"disabled": False}),
                       ("u9", {"email": "new@example.com", "email_verified": True})]


def test_mock_admin_round_trip():
    store = MockIdentities()
    admin = MockIdentityAdmin(store)
    uid = admin.create_user(" New@example.com ", "New")
    assert uid == "mock-uid-1"
    with pytest.raises(IdentityExists):
        admin.create_user("new@example.com")
    got = admin.get_user(email="NEW@example.com")
    assert got["uid"] == uid and got["disabled"] is False and got["providers"] == ["password"]
    assert admin.get_user(uid=uid)["email"] == "new@example.com" and admin.get_user(uid="zzz") is None
    admin.set_password(uid, "pw")
    admin.disable_user(uid)
    assert admin.get_user(uid=uid)["disabled"] is True
    admin.disable_user(uid, False)
    admin.revoke_sessions(uid)
    admin.update_email(uid, "moved@example.com")
    assert admin.get_user(email="new@example.com") is None
    admin.send_password_reset("moved@example.com", "es")
    assert store.sent_mails == [("moved@example.com", "es")]
    assert admin.password_reset_link("moved@example.com").startswith("https://mock.invalid/")
    admin.delete_user(uid)
    with pytest.raises(IdentityNotFound):
        admin.delete_user(uid)


def test_mock_failure_switches():
    store = MockIdentities()
    admin = MockIdentityAdmin(store)
    admin.create_user("a@example.com")
    store.fail_mail = True
    with pytest.raises(MailNotSent):
        admin.send_password_reset("a@example.com")
    store.fail_link = True
    with pytest.raises(AuthUnavailable):
        admin.password_reset_link("a@example.com")
    store.unavailable = True
    with pytest.raises(AuthUnavailable):
        admin.get_user(email="a@example.com")
    with pytest.raises(MailNotSent):
        admin.send_password_reset("nobody@example.com")
    assert ("create", "a@example.com") in store.calls
