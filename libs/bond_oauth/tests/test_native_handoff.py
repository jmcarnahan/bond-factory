"""Native-app flow: an unbound state marked native, and the one-time hand-off code."""

import pytest
from conftest import Connection

from bond_oauth import (
    OAuthError,
    PendingConnection,
    complete,
    decode_state,
    encode_state,
    issue_handoff,
    redeem_handoff,
    start_flow,
)
from bond_oauth.handoff import forget_handoffs


@pytest.fixture(autouse=True)
def _clean_handoffs():
    forget_handoffs()
    yield
    forget_handoffs()


def begin(session, cipher, fake, *, native, user="u1", **kw):
    return start_flow(session, user_id=user, provider_name="fake", provider=fake, scopes=["openid", "email"],
                      redirect_to="sdkdemo://connections", cipher=cipher, redirect_uri="http://cb", native=native, **kw)


def finish(session, cipher, providers, flow, **kw):
    kw.setdefault("expected_user_id", None)
    return complete(session, state=flow.state, code="mock", providers=providers, cipher=cipher,
                    connection_model=Connection, redirect_uri="http://cb", **kw)


def redeem(session, cipher, code, user="u1", **kw):
    return redeem_handoff(session, code=code, user_id=user, cipher=cipher, connection_model=Connection, **kw)


def test_native_state_round_trip(session, cipher, fake):
    flow = begin(session, cipher, fake, native=True)
    assert decode_state(cipher, flow.state).native is True
    assert decode_state(cipher, begin(session, cipher, fake, native=False).state).native is False


def test_native_flag_survives_an_old_state_without_it(cipher):
    state = encode_state(cipher, sub="u1", provider="fake", connection_name="fake", verifier="v", redirect_to="x")
    assert decode_state(cipher, state).native is False


def rows(session, **filters):
    return session.query(Connection).filter_by(**filters).count()


def test_native_complete_returns_a_pending_connection_and_stores_nothing(session, cipher, fake, providers):
    pending = finish(session, cipher, providers, begin(session, cipher, fake, native=True), expected_nonce=None)
    assert isinstance(pending, PendingConnection) and pending.owner == "u1"
    assert pending.fields["account_email"] and rows(session) == 0


def test_complete_without_a_nonce_is_refused_for_web(session, cipher, fake, providers):
    flow = begin(session, cipher, fake, native=False)
    with pytest.raises(OAuthError) as err:
        finish(session, cipher, providers, flow, expected_nonce=None)
    assert err.value.code == "invalid_state"


def test_native_with_a_wrong_nonce_is_still_refused(session, cipher, fake, providers):
    with pytest.raises(OAuthError) as err:
        finish(session, cipher, providers, begin(session, cipher, fake, native=True), expected_nonce="nope")
    assert err.value.code == "invalid_state"


def sealed(session, cipher, fake, providers, **kw):
    pending = finish(session, cipher, providers, begin(session, cipher, fake, native=True, **kw), expected_nonce=None)
    return issue_handoff(pending, cipher=cipher)


def test_handoff_mint_and_redeem_inserts_the_row(session, cipher, fake, providers):
    code = sealed(session, cipher, fake, providers)
    assert rows(session) == 0
    row = redeem(session, cipher, code)
    assert row.user_id == "u1" and row.revoked_at is None and rows(session) == 1
    assert cipher.decrypt(row.refresh_token_enc) and row.expires_at is not None and row.connected_at is not None


def test_redeem_twice_fails_and_stores_nothing_more(session, cipher, fake, providers):
    code = sealed(session, cipher, fake, providers)
    redeem(session, cipher, code)
    with pytest.raises(OAuthError) as err:
        redeem(session, cipher, code)
    assert err.value.code == "invalid_handoff" and rows(session) == 1


def test_wrong_user_fails_leaves_no_row_and_does_not_burn_the_code(session, cipher, fake, providers):
    code = sealed(session, cipher, fake, providers)
    with pytest.raises(OAuthError) as err:
        redeem(session, cipher, code, user="u2")
    assert err.value.code == "invalid_handoff" and rows(session) == 0
    assert redeem(session, cipher, code).user_id == "u1"


def test_expired_code_fails_and_stores_nothing(session, cipher, fake, providers):
    pending = finish(session, cipher, providers, begin(session, cipher, fake, native=True), expected_nonce=None)
    code = issue_handoff(pending, cipher=cipher, ttl=120, now=1000.0)
    with pytest.raises(OAuthError) as err:
        redeem(session, cipher, code, now=1120.0)
    assert err.value.code == "invalid_handoff" and rows(session) == 0
    assert redeem(session, cipher, code, now=1119.0).user_id == "u1"


def test_garbage_and_state_blobs_are_not_codes(session, cipher, fake):
    for bad in ("", "nonsense", begin(session, cipher, fake, native=True).state):
        with pytest.raises(OAuthError) as err:
            redeem(session, cipher, bad)
        assert err.value.code == "invalid_handoff"
    assert rows(session) == 0


def test_redeem_revokes_the_older_live_row(session, cipher, fake, providers):
    first = redeem(session, cipher, sealed(session, cipher, fake, providers))
    second = redeem(session, cipher, sealed(session, cipher, fake, providers))
    session.refresh(first)
    assert first.revoked_at is not None and second.revoked_at is None and rows(session, revoked_at=None) == 1


def test_shared_native_flow_gets_no_handoff(session, cipher, fake, providers):
    pending = finish(session, cipher, providers, begin(session, cipher, fake, native=True, shared=True),
                     expected_nonce=None)
    with pytest.raises(OAuthError):
        issue_handoff(pending, cipher=cipher)
