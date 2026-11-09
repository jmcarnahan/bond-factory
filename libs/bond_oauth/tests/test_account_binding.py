"""Connect flow account binding: ``login_hint`` and ``expected_subject``."""

import pytest
from conftest import Connection, connect, nonce_of, stat

from bond_oauth import FakeOAuth, OAuthError, complete, decode_state, start_flow
from bond_oauth.fake import mock_code


def begin(session, cipher, fake, scopes=("openid", "email"), name="fake", **kw):
    return start_flow(session, user_id="u1", provider_name=name, provider=fake, scopes=list(scopes),
                      redirect_to="http://app/x", cipher=cipher, redirect_uri="http://cb", **kw)


def finish(session, cipher, fake, flow, code="mock", name="fake"):
    return complete(session, state=flow.state, code=code, providers={name: fake}, cipher=cipher,
                    connection_model=Connection, redirect_uri="http://cb", expected_nonce=flow.nonce,
                    expected_user_id="u1")


MS = "fake-microsoft"


def subject_of(fake, email):
    return fake._ids(email)[0]


def test_login_hint_goes_to_the_provider_and_the_state(session, cipher, fake):
    flow = begin(session, cipher, fake, login_hint="ann@example.com")
    assert "hint=ann%40example.com" in flow.authorize_url
    assert decode_state(cipher, flow.state).login_hint == "ann@example.com"


def test_no_login_hint_keeps_the_old_url_and_works_with_a_provider_that_predates_it(session, cipher):
    class Old:
        def authorize_url(self, *, state, challenge, scopes, redirect_uri):
            return "/old"

    assert begin(session, cipher, Old()).authorize_url == "/old"


def test_matching_subject_connects(session, cipher, fake):
    flow = begin(session, cipher, fake, expected_subject=subject_of(fake, "demo@example.com"))
    assert finish(session, cipher, fake, flow).account_email == "demo@example.com"


def test_other_account_is_refused_account_mismatch_and_stores_nothing(session, cipher, fake):
    flow = begin(session, cipher, fake, expected_subject=subject_of(fake, "demo@example.com"))
    with pytest.raises(OAuthError) as caught:
        finish(session, cipher, fake, flow, code=mock_code("someone.else@example.com"))
    assert caught.value.code == "account_mismatch"
    assert session.query(Connection).count() == 0


def test_shared_connect_skips_the_check(session, cipher, fake):
    flow = begin(session, cipher, fake, shared=True, expected_subject="not-this-one")
    assert finish(session, cipher, fake, flow, code=mock_code("office@example.com")).user_id is None


def test_no_expected_subject_means_no_check(session, cipher, fake):
    assert connect(session, cipher, fake, {"fake": fake}).account_email == "demo@example.com"
    assert stat(session).connected


def test_native_connect_checks_the_account_before_a_pending_connection_exists(session, cipher, fake):
    flow = begin(session, cipher, fake, native=True, expected_subject="x-different")
    with pytest.raises(OAuthError) as caught:
        complete(session, state=flow.state, code="mock", providers={"fake": fake}, cipher=cipher,
                 connection_model=Connection, redirect_uri="http://cb", expected_nonce=None, expected_user_id=None)
    assert caught.value.code == "account_mismatch"


def test_microsoft_subject_is_tid_colon_oid(session, cipher):
    ms = FakeOAuth("/c", kind="microsoft", pinned_tenant="11111111-2222-4333-8444-555555555555")
    good = f"11111111-2222-4333-8444-555555555555:{ms._ids('demo@example.com')[1]}"
    flow = begin(session, cipher, ms, ("openid", "offline_access"), name=MS, expected_subject=good)
    assert finish(session, cipher, ms, flow, name=MS).account_email == "demo@example.com"
    bad = begin(session, cipher, ms, ("openid", "offline_access"), name=MS, expected_subject="other-tenant:" + good.split(":")[1])
    with pytest.raises(OAuthError) as caught:
        finish(session, cipher, ms, bad, name=MS)
    assert caught.value.code == "account_mismatch"


def test_without_an_id_token_the_userinfo_subject_is_used(session, cipher, fake):
    class NoIdToken(FakeOAuth):
        def exchange(self, **kw):
            tokens = super().exchange(**kw)
            tokens.raw.pop("id_token")
            return tokens

    plain = NoIdToken("/c")
    ok = begin(session, cipher, plain, expected_subject=subject_of(plain, "demo@example.com"))
    assert finish(session, cipher, plain, ok).account_email == "demo@example.com"
    no = begin(session, cipher, plain, expected_subject="nope")
    with pytest.raises(OAuthError) as caught:
        finish(session, cipher, plain, no)
    assert caught.value.code == "account_mismatch" and nonce_of(cipher, no.state)


def test_a_provider_that_exposes_no_subject_fails_closed(session, cipher):
    class Blank(FakeOAuth):
        def exchange(self, **kw):
            tokens = super().exchange(**kw)
            tokens.raw.pop("id_token")
            return tokens

        def userinfo(self, access_token):
            return {"email": "demo@example.com"}

    blank = Blank("/c")
    flow = begin(session, cipher, blank, expected_subject="anything")
    with pytest.raises(OAuthError) as caught:
        finish(session, cipher, blank, flow)
    assert caught.value.code == "account_mismatch"


def test_start_flow_stores_device_hash_and_attempt_id(session, cipher, fake):
    flow = begin(session, cipher, fake, native=True, device_hash="ab" * 32, attempt_id="att_1-x")
    state = decode_state(cipher, flow.state)
    assert (state.device_hash, state.attempt_id, state.native) == ("ab" * 32, "att_1-x", True)


def test_start_flow_defaults_leave_both_unset(session, cipher, fake):
    state = decode_state(cipher, begin(session, cipher, fake).state)
    assert state.device_hash is None and state.attempt_id is None


@pytest.mark.parametrize("kw", [{"device_hash": "AB" * 32}, {"device_hash": "ab" * 31}, {"device_hash": ""},
                                {"attempt_id": "a b"}, {"attempt_id": ""}, {"attempt_id": "a" * 65}])
def test_start_flow_validates_both(session, cipher, fake, kw):
    with pytest.raises(OAuthError) as caught:
        begin(session, cipher, fake, **kw)
    assert caught.value.code == "invalid_request"


def test_store_connection_is_exported():
    import bond_oauth
    assert bond_oauth.store_connection is bond_oauth.service.store_connection
