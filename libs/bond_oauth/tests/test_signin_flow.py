"""``SignInFlow``: start, complete (bindings, refusals) and store."""

from urllib.parse import parse_qs, urlparse

import pytest
from conftest import Connection
from jwt_util import TID

from bond_oauth import (
    GOOGLE_MAIL_SEND,
    GOOGLE_SIGNIN,
    MICROSOFT_SIGNIN_FULL,
    FakeOAuth,
    OAuthError,
    SignInFlow,
    decode_state,
    encode_state,
    pkce,
)
from bond_oauth.fake import mock_code

BASE = "https://api.example.test"
DEVICE = "ab" * 32
MAIL = list(GOOGLE_SIGNIN + GOOGLE_MAIL_SEND)


def make_flow(cipher, *, clock=None, pinned=None, **fake_kw):
    fakes = {"fake-google": FakeOAuth("/consent", **fake_kw),
             "fake-microsoft": FakeOAuth("/consent", kind="microsoft", pinned_tenant=TID, **fake_kw)}
    kw = {"clock": clock} if clock else {}
    flow = SignInFlow(providers=fakes, cipher=cipher, client_ids={"fake-google": "fake-client",
                      "fake-microsoft": "fake-client"}, public_base=BASE + "/", pinned_tenants=pinned, **kw)
    return flow, fakes


def rows(session):
    return session.query(Connection).count()


def test_callback_url_and_start_result(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="https://app.example/x")
    assert flow.callback_url("google") == f"{BASE}/auth/signin/google/callback"
    state = decode_state(cipher, started.state)
    assert (state.intent, state.sub, state.nonce, state.native) == ("signin", None, started.nonce, False)
    assert state.oidc_nonce and state.oidc_nonce != started.nonce and len(state.oidc_nonce) == 64
    assert started.url.startswith("/consent?state=")


def test_start_hands_the_provider_pkce_nonce_and_callback(cipher):
    seen = {}

    class Spy(FakeOAuth):
        def authorize_url(self, **kw):
            seen.update(kw)
            return super().authorize_url(**kw)

    flow = SignInFlow(providers={"fake-google": Spy("/c")}, cipher=cipher, client_ids={"fake-google": "x"},
                      public_base=BASE)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r")
    state = decode_state(cipher, started.state)
    assert seen["challenge"] == pkce.challenge(state.verifier)
    assert seen["nonce"] == state.oidc_nonce and seen["redirect_uri"] == f"{BASE}/auth/signin/fake-google/callback"
    assert (seen["offline"], seen["prompt"]) == (False, "select_account")


def test_start_asks_offline_consent_only_beyond_identity(cipher):
    seen = []

    class Spy(FakeOAuth):
        def authorize_url(self, **kw):
            seen.append(kw)
            return super().authorize_url(**kw)

    flow = SignInFlow(providers={"fake-google": Spy("/c"), "fake-microsoft": Spy("/c", kind="microsoft")},
                      cipher=cipher, client_ids={"fake-google": "x", "fake-microsoft": "x"}, public_base=BASE)
    flow.start(provider="fake-google", scopes=MAIL, redirect_to="r")
    flow.start(provider="fake-microsoft", scopes=MICROSOFT_SIGNIN_FULL, redirect_to="r")
    assert (seen[0]["offline"], seen[0]["prompt"]) == (True, "consent")
    assert (seen[1]["offline"], seen[1]["prompt"]) == (True, "select_account")  # deviation: Microsoft never forces consent


def test_start_validates_inputs(cipher):
    flow, _ = make_flow(cipher)
    for bad in ({"provider": "nope"}, {"device_hash": "XY"}, {"device_hash": "A" * 64}, {"attempt_id": "a b"},
                {"attempt_id": "a" * 65}):
        kw = {"provider": "fake-google", "scopes": GOOGLE_SIGNIN, "redirect_to": "r", **bad}
        with pytest.raises(OAuthError):
            flow.start(**kw)


def test_a_provider_without_a_client_id_is_refused_at_construction(cipher):
    with pytest.raises(ValueError):
        SignInFlow(providers={"google": FakeOAuth("/c")}, cipher=cipher, client_ids={}, public_base=BASE)


def test_web_signin_round_trip_identity_only_has_no_pending(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="https://app.example/x",
                         attempt_id="att-1")
    result = flow.complete(state=started.state, code=mock_code("ANN@example.com"), expected_nonce=started.nonce,
                           expected_device_hash=None)
    assert result.identity.email == "ann@example.com" and result.identity.email_verified is True
    assert result.pending is None and result.native is False and result.set_id is None
    assert (result.redirect_to, result.attempt_id) == ("https://app.example/x", "att-1")
    assert result.granted_scopes == list(GOOGLE_SIGNIN)


def test_signin_with_mail_scope_returns_a_pending_connection(cipher, session):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=MAIL, redirect_to="r")
    result = flow.complete(state=started.state, code="mock", expected_nonce=started.nonce, expected_device_hash=None)
    assert result.pending is not None and result.pending.owner is None
    assert result.pending.fields["account_email"] == "demo@example.com" and rows(session) == 0
    row = flow.store(session, Connection, owner="u1", result=result)
    assert (row.user_id, row.provider, row.connection_name, row.revoked_at) == ("u1", "fake-google", "fake-google", None)
    assert cipher.decrypt(row.refresh_token_enc).startswith("fake-refresh-")


def test_identity_only_store_returns_none_and_stores_nothing(cipher, session):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r")
    result = flow.complete(state=started.state, code="mock", expected_nonce=started.nonce, expected_device_hash=None)
    assert flow.store(session, Connection, owner="u1", result=result) is None and rows(session) == 0


def test_declining_the_mail_set_leaves_identity_only_and_no_pending(cipher):
    flow, _ = make_flow(cipher, set_scopes={"mail": GOOGLE_MAIL_SEND})
    started = flow.start(provider="fake-google", scopes=MAIL, redirect_to="r")
    result = flow.complete(state=started.state, code=mock_code("a@example.com", ["mail"]),
                           expected_nonce=started.nonce, expected_device_hash=None)
    assert result.granted_scopes == list(GOOGLE_SIGNIN) and result.pending is None


def test_store_revokes_the_previous_live_row(cipher, session):
    flow, _ = make_flow(cipher)
    rows_made = []
    for _ in range(2):
        started = flow.start(provider="fake-google", scopes=MAIL, redirect_to="r")
        result = flow.complete(state=started.state, code="mock", expected_nonce=started.nonce,
                               expected_device_hash=None)
        rows_made.append(flow.store(session, Connection, owner="u1", result=result, connection_name="mail"))
    live = session.query(Connection).filter(Connection.revoked_at.is_(None)).all()
    assert [r.id for r in live] == [rows_made[1].id] and rows(session) == 2


def test_microsoft_signin_full_scopes_gives_pending_and_tenant_identity(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-microsoft", scopes=MICROSOFT_SIGNIN_FULL, redirect_to="r")
    result = flow.complete(state=started.state, code="mock", expected_nonce=started.nonce, expected_device_hash=None)
    assert result.identity.tenant == TID and result.identity.subject.startswith(TID + ":")
    assert result.identity.email_verified is True and result.pending is not None


def test_microsoft_other_tenant_from_the_flow_mapping_is_tenant_mismatch(cipher):
    flow, _ = make_flow(cipher, pinned={"fake-microsoft": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"})
    started = flow.start(provider="fake-microsoft", scopes=MICROSOFT_SIGNIN_FULL, redirect_to="r")
    with pytest.raises(OAuthError) as caught:
        flow.complete(state=started.state, code="mock", expected_nonce=started.nonce, expected_device_hash=None)
    assert caught.value.code == "tenant_mismatch"


def test_native_signin_binds_the_device_hash(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r", device_hash=DEVICE)
    assert decode_state(cipher, started.state).native is True
    result = flow.complete(state=started.state, code="mock", expected_nonce=None, expected_device_hash=DEVICE)
    assert result.native is True


def started_variants(cipher):
    flow, _ = make_flow(cipher)
    web = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r")
    native = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r", device_hash=DEVICE)
    return flow, web, native


@pytest.mark.parametrize("case", ["connect_state", "wrong_nonce", "no_nonce", "native_wrong_hash",
                                  "native_no_hash", "native_with_nonce_only", "bad_code", "garbage_state",
                                  "expired", "wrong_provider_id_token_nonce"])
def test_refusals_store_nothing(cipher, session, case):
    flow, web, native = started_variants(cipher)
    args = {"state": web.state, "code": "mock", "expected_nonce": web.nonce, "expected_device_hash": None}
    expect = "invalid_state"
    if case == "connect_state":
        v = decode_state(cipher, web.state)
        args["state"] = encode_state(cipher, sub="u1", provider="fake-google", connection_name="x", verifier=v.verifier,
                                     redirect_to="r", nonce=web.nonce)
    elif case == "wrong_nonce":
        args["expected_nonce"] = "someone-elses"
    elif case == "no_nonce":
        args["expected_nonce"] = None
    elif case.startswith("native"):
        args.update(state=native.state, expected_nonce=native.nonce if case.endswith("only") else None,
                    expected_device_hash={"native_wrong_hash": "cd" * 32}.get(case))
    elif case == "bad_code":
        args["code"], expect = "garbage", "invalid_code"
    elif case == "garbage_state":
        args["state"] = "zzz"
    elif case == "expired":
        v = decode_state(cipher, web.state)
        args["state"] = encode_state(cipher, sub=None, provider="fake-google", connection_name="x", verifier=v.verifier,
                                     redirect_to="r", intent="signin", nonce=web.nonce, oidc_nonce=v.oidc_nonce,
                                     now=1.0)
        expect = "signin_expired"
    elif case == "wrong_provider_id_token_nonce":
        v = decode_state(cipher, web.state)
        args["state"] = encode_state(cipher, sub=None, provider="fake-google", connection_name="x", verifier=v.verifier,
                                     redirect_to="r", intent="signin", nonce=web.nonce, oidc_nonce="f" * 64)
        expect = "invalid_id_token"
    with pytest.raises(OAuthError) as caught:
        flow.complete(**args)
    assert caught.value.code == expect and rows(session) == 0


def test_an_expired_connect_state_is_invalid_not_signin_expired(cipher):
    flow, _ = make_flow(cipher)
    state = encode_state(cipher, sub="u1", provider="fake-google", connection_name="x", verifier="v", redirect_to="r",
                         now=1.0)
    with pytest.raises(OAuthError) as caught:
        flow.complete(state=state, code="mock", expected_nonce="n", expected_device_hash=None)
    assert caught.value.code == "invalid_state"


def test_an_expired_id_token_is_refused_by_the_flow_clock(cipher):
    flow, _ = make_flow(cipher)  # the fake mints exp = now + 1h on the real clock
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r")
    flow._clock = lambda: 4_000_000_000.0
    with pytest.raises(OAuthError) as caught:
        flow.complete(state=started.state, code="mock", expected_nonce=started.nonce, expected_device_hash=None)
    assert caught.value.code == "invalid_id_token"


def test_userinfo_failure_does_not_fail_the_signin(cipher):
    flow, fakes = make_flow(cipher)

    def broken(token):
        raise OAuthError("userinfo_failed")

    fakes["fake-google"].userinfo = broken
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r")
    result = flow.complete(state=started.state, code="mock", expected_nonce=started.nonce, expected_device_hash=None)
    assert result.identity.email == "demo@example.com"


def test_signin_state_is_not_a_connect_state(cipher, session, providers):
    """The connect ``complete`` refuses a sign-in state (it would otherwise store under owner None)."""
    from bond_oauth import complete
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r")
    with pytest.raises(OAuthError) as caught:
        complete(session, state=started.state, code="mock", providers={"fake-google": FakeOAuth("/c")}, cipher=cipher,
                 connection_model=Connection, redirect_uri="r", expected_nonce=started.nonce, expected_user_id=None)
    assert caught.value.code == "invalid_state" and rows(session) == 0
    assert parse_qs(urlparse(started.url).query)["state"][0] == started.state


def test_peek_reads_the_state_without_the_verifier(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="https://app.example/x",
                         attempt_id="att-1", device_hash=DEVICE)
    info = flow.peek(state=started.state)
    assert (info.redirect_to, info.attempt_id, info.native, info.nonce, info.device_hash, info.provider,
            info.set_id) == ("https://app.example/x", "att-1", True, started.nonce, DEVICE, "fake-google", None)
    web = flow.peek(state=flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r").state)
    assert web.native is False and web.device_hash is None


def test_peek_refuses_unauthentic_states_and_flags_expired_ones(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r")
    v = decode_state(cipher, started.state)
    expired = encode_state(cipher, sub=None, provider="fake-google", connection_name="x", verifier=v.verifier,
                           redirect_to="r", intent="signin", oidc_nonce="o", now=1.0)
    connect = encode_state(cipher, sub="u1", provider="fake-google", connection_name="x", verifier="v", redirect_to="r")
    for state in ("zzz", connect):
        with pytest.raises(OAuthError) as caught:
            flow.peek(state=state)
        assert caught.value.code == "invalid_state"
    info = flow.peek(state=expired)  # authentic but expired: returned, flagged; complete() raises
    assert info.expired is True and info.redirect_to == "r" and flow.peek(state=started.state).expired is False
    with pytest.raises(OAuthError) as caught:
        flow.complete(state=expired, code="mock", expected_nonce="n", expected_device_hash=None)
    assert caught.value.code == "signin_expired"


def test_reprs_hide_the_nonce_state_and_pending(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=MAIL, redirect_to="r")
    result = flow.complete(state=started.state, code="mock", expected_nonce=started.nonce, expected_device_hash=None)
    assert result.pending is not None
    shown = repr(started) + repr(result)
    assert started.nonce not in shown and started.state not in shown and "fake-refresh" not in shown
    assert "refresh_token_enc" not in shown and "access_token_enc" not in shown


@pytest.mark.parametrize("pin", ["common", "organizations", "consumers", "", None, "tid-1", TID + "0"])
def test_a_real_microsoft_provider_needs_a_guid_pin(cipher, pin):
    from jwt_util import microsoft
    ms = microsoft(None)
    ms.pinned_tenant = pin  # bypass the constructor check to prove the flow checks as well
    with pytest.raises(ValueError, match="microsoft"):
        SignInFlow(providers={"microsoft": ms}, cipher=cipher, client_ids={"microsoft": "c"}, public_base=BASE)


def test_a_guid_pin_from_the_provider_or_the_mapping_is_accepted(cipher):
    from jwt_util import microsoft
    SignInFlow(providers={"microsoft": microsoft(TID)}, cipher=cipher, client_ids={"microsoft": "c"}, public_base=BASE)
    SignInFlow(providers={"microsoft": microsoft(None)}, cipher=cipher, client_ids={"microsoft": "c"},
               public_base=BASE, pinned_tenants={"microsoft": TID.upper()})
    with pytest.raises(ValueError):
        SignInFlow(providers={"microsoft": microsoft(None)}, cipher=cipher, client_ids={"microsoft": "c"},
                   public_base=BASE, pinned_tenants={"microsoft": "common"})


def test_a_fake_microsoft_provider_is_exempt_from_the_pin(cipher):
    SignInFlow(providers={"fake-microsoft": FakeOAuth("/c", kind="microsoft")}, cipher=cipher,
               client_ids={"fake-microsoft": "c"}, public_base=BASE)


def test_state_info_repr_hides_nonce_and_device_hash(cipher):
    flow, _ = make_flow(cipher)
    started = flow.start(provider="fake-google", scopes=GOOGLE_SIGNIN, redirect_to="r", device_hash=DEVICE)
    shown = repr(flow.peek(state=started.state))
    assert started.nonce not in shown and DEVICE not in shown


def test_a_real_microsoft_provider_fails_closed_when_me_fails(cipher):
    import httpx
    from jwt_util import CLIENT, make_jwt, microsoft_claims

    from bond_oauth import MicrosoftOAuth

    def handler(request):
        if "/token" in request.url.path:
            return httpx.Response(200, json={"access_token": "a", "id_token": make_jwt(
                microsoft_claims(nonce=NONCE[0], exp=4_000_000_000))})
        return httpx.Response(500)  # /me is down

    NONCE = [""]
    ms = MicrosoftOAuth("c", "s", tenant=TID, http=httpx.Client(transport=httpx.MockTransport(handler)),
                        pinned_tenant=TID)
    flow = SignInFlow(providers={"microsoft": ms}, cipher=cipher, client_ids={"microsoft": CLIENT}, public_base=BASE)
    started = flow.start(provider="microsoft", scopes=("openid", "profile", "email"), redirect_to="r")
    NONCE[0] = decode_state(cipher, started.state).oidc_nonce
    from bond_oauth import RetryableError
    with pytest.raises((OAuthError, RetryableError)):
        flow.complete(state=started.state, code="c", expected_nonce=started.nonce, expected_device_hash=None)
