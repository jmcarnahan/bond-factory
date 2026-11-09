import json
from dataclasses import replace

import pytest

from bond_auth_py import (
    AUTH_UNAVAILABLE,
    AuthNotConfigured,
    AuthRefused,
    AuthSettings,
    AuthUnavailable,
    EmailNotVerified,
    Identity,
    MockIdentities,
    TokenError,
    default_mock,
    register_mock_token,
    set_verifier,
    verify_id_token,
)


def test_injected_object_wins_over_everything(mock_settings):
    class Fake:
        def verify(self, token):
            if token == "bad":
                raise TokenError("invalid")
            return {"uid": "u1", "email": " Jess@example.com ", "name": "Jess", "auth_time": 5,
                    "sign_in_provider": "google.com", "identities": {"google.com": ["1"]}}

    set_verifier(Fake())
    got = verify_id_token("good", mock_settings)
    assert got == Identity("u1", "jess@example.com", "Jess", 5.0, "google.com", {"google.com": ["1"]})
    with pytest.raises(TokenError):
        verify_id_token("bad", mock_settings)


def test_injected_callable_and_identity_result(settings):
    set_verifier(lambda token: Identity("u2", "a@example.com"))
    assert verify_id_token("x", settings).uid == "u2"


def test_injected_tier_without_verifier_is_unavailable():
    with pytest.raises(AuthUnavailable):
        verify_id_token("x", AuthSettings(tier="injected"))


def test_incomplete_results_are_refused(settings):
    set_verifier(lambda token: {"uid": "", "email": "a@example.com"})
    with pytest.raises(TokenError) as err:
        verify_id_token("x", settings)
    assert err.value.reason == "incomplete"
    set_verifier(lambda token: {"uid": "u", "email": "  "})
    with pytest.raises(TokenError):
        verify_id_token("x", settings)


def test_malformed_tokens(mock_settings):
    for token in ("", "   ", None, "x" * 8193):
        with pytest.raises(TokenError) as err:
            verify_id_token(token, mock_settings)
        assert err.value.reason == "malformed"
    assert verify_id_token("mock:" + "a" * 8000 + "@example.com", mock_settings).email.endswith("@example.com")


def test_mock_literal_and_known_uid(mock_settings):
    got = verify_id_token("mock:Someone@example.com", mock_settings)
    assert (got.uid, got.email, got.sign_in_provider) == ("mock-someone@example.com", "someone@example.com", "password")
    assert got.auth_time is not None
    uid = default_mock().seed("known@example.com", "Known")
    assert uid == "mock-uid-1"
    assert verify_id_token("mock:known@example.com", mock_settings).uid == uid
    with pytest.raises(TokenError):
        verify_id_token("mock:not-an-email", mock_settings)


def test_mock_registered_expired_and_disabled(mock_settings):
    register_mock_token("t1", "uid-1", "A@example.com", "A", provider="google.com",
                        identities={"google.com": ["g1"]}, auth_time=100.0)
    got = verify_id_token("t1", mock_settings)
    assert (got.uid, got.email, got.auth_time, got.sign_in_provider) == ("uid-1", "a@example.com", 100.0, "google.com")
    register_mock_token("old", "uid-2", "b@example.com", expired=True)
    with pytest.raises(TokenError) as err:
        verify_id_token("old", mock_settings)
    assert err.value.reason == "expired"
    uid = default_mock().seed("c@example.com")
    register_mock_token("c", uid, "c@example.com")
    default_mock().set_disabled(uid, True)
    with pytest.raises(TokenError):
        verify_id_token("c", mock_settings)


def test_mock_is_only_active_under_test(monkeypatch, fake_firebase):
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    outside = AuthSettings(tier="mock")
    with pytest.raises(AuthUnavailable):  # mock refused, falls to firebase, which is not configured
        verify_id_token("mock:a@example.com", outside)
    assert verify_id_token("mock:a@example.com", replace(outside, test_env=True)).email == "a@example.com"
    assert verify_id_token("mock:a@example.com", replace(outside, mock_enabled_only_under_test=False)).uid


def test_own_mock_instance(mock_settings):
    mine = MockIdentities()
    mine.register_mock_token("t", "u", "a@example.com")
    assert verify_id_token("t", mock_settings, mock=mine).uid == "u"
    with pytest.raises(TokenError):
        verify_id_token("t", mock_settings)  # the default mock does not know it


def test_mock_identities_file(tmp_path, mock_settings):
    path = tmp_path / "ids.json"
    path.write_text(json.dumps([{"email": "A@example.com", "name": "A", "token": "tok-a"},
                                {"email": "b@example.com", "uid": "fixed-uid", "token": "tok-b"}]))
    assert default_mock().load_file(str(path)) == 2
    assert verify_id_token("tok-a", mock_settings).uid == "mock-uid-1"
    assert verify_id_token("tok-b", mock_settings).uid == "fixed-uid"
    path.write_text("{}")
    with pytest.raises(TypeError):
        default_mock().load_file(str(path))


# -- the firebase tier through a fake firebase_admin ---------------------------------------------------------------------


def firebase_settings(**kw):
    return AuthSettings(firebase_project_id="demo-example", **kw)


def test_firebase_not_configured_is_unavailable(settings, fake_firebase):
    with pytest.raises(AuthUnavailable):
        verify_id_token("tok", settings)


def test_firebase_tier_claims_and_revocation_check(fake_firebase, monkeypatch):
    from conftest import service_account

    calls = []

    def fake_verify(token, app=None, check_revoked=False):
        calls.append(check_revoked)
        return {"uid": "u1", "email": "Someone@example.com", "email_verified": True, "name": "S", "auth_time": 7,
                "firebase": {"sign_in_provider": "apple.com", "identities": {"apple.com": ["a"]}}}

    monkeypatch.setattr(fake_firebase.auth, "verify_id_token", fake_verify)
    got = verify_id_token("tok", firebase_settings())
    assert (got.uid, got.email, got.sign_in_provider, got.auth_time) == ("u1", "someone@example.com", "apple.com", 7.0)
    verify_id_token("tok", firebase_settings(service_account_json=service_account()))
    assert calls == [False, True]  # check_revoked only with a service account


def test_firebase_unverified_and_missing_email(fake_firebase, monkeypatch):
    claims = {"uid": "u", "email": "a@example.com", "email_verified": False}
    monkeypatch.setattr(fake_firebase.auth, "verify_id_token", lambda t, app=None, **kw: claims)
    with pytest.raises(EmailNotVerified):
        verify_id_token("tok", firebase_settings())
    claims.pop("email")
    with pytest.raises(TokenError) as err:
        verify_id_token("tok", firebase_settings())
    assert err.value.reason == "incomplete"


@pytest.mark.parametrize(("error", "reason"), [
    ("ExpiredIdTokenError", "expired"), ("InvalidIdTokenError", "invalid"), ("RevokedIdTokenError", "invalid"),
    ("UserDisabledError", "invalid"),
])
def test_firebase_errors_map_to_token_error(fake_firebase, monkeypatch, error, reason):
    def boom(token, app=None, **kw):
        raise getattr(fake_firebase.auth, error)("x")

    monkeypatch.setattr(fake_firebase.auth, "verify_id_token", boom)
    with pytest.raises(TokenError) as err:
        verify_id_token("tok", firebase_settings())
    assert err.value.reason == reason


CertificateFetchError = type("CertificateFetchError", (Exception,), {})  # firebase-admin's, matched by name
TransportError = type("TransportError", (Exception,), {})  # google.auth's
RequestException = type("RequestException", (Exception,), {})  # requests'


@pytest.mark.parametrize("error", [
    CertificateFetchError("certs"), TransportError("down"), RequestException("dns"),
    ConnectionError("refused"), TimeoutError("slow"), OSError("network unreachable"),
])
def test_transport_and_certificate_failures_are_an_outage_not_a_rejection(fake_firebase, monkeypatch, error):
    def boom(token, app=None, **kw):
        raise error

    monkeypatch.setattr(fake_firebase.auth, "verify_id_token", boom)
    with pytest.raises(AuthUnavailable) as err:
        verify_id_token("tok", firebase_settings())
    assert not isinstance(err.value, AuthNotConfigured) and not isinstance(err.value, TokenError)


def test_other_unexpected_errors_are_still_a_rejection_not_a_500(fake_firebase, monkeypatch):
    def boom(token, app=None, **kw):
        raise RuntimeError("something odd")

    monkeypatch.setattr(fake_firebase.auth, "verify_id_token", boom)
    with pytest.raises(TokenError):
        verify_id_token("tok", firebase_settings())
    monkeypatch.setattr(fake_firebase.auth, "verify_id_token", lambda t, app=None, **kw: {"uid": "u"})
    with pytest.raises(TokenError):  # no e-mail
        verify_id_token("tok", firebase_settings())


def test_not_configured_is_distinct_from_an_outage(settings, fake_firebase):
    with pytest.raises(AuthNotConfigured):
        verify_id_token("tok", settings)
    with pytest.raises(AuthNotConfigured):
        verify_id_token("tok", AuthSettings(tier="injected"))
    assert issubclass(AuthNotConfigured, AuthUnavailable)
    assert AuthRefused(AUTH_UNAVAILABLE).status == 503
