import time
from datetime import datetime
from urllib.parse import unquote

import pytest
from conftest import SCOPES, Connection, connect, nonce_of, stat
from sqlalchemy import select

from bond_oauth import (
    OAuthError,
    ReconnectRequired,
    RetryableError,
    access_token,
    complete,
    decode_state,
    disconnect,
    encode_state,
    pkce,
    start,
    start_flow,
    status,
)


def test_start_returns_consent_url_with_encrypted_state(session, cipher, fake):
    url = start(session, user_id="u1", provider_name="fake", provider=fake, scopes=SCOPES, redirect_to="http://app/x",
                cipher=cipher, redirect_uri="http://cb")
    assert url.startswith("/consent?state=")


def test_complete_stores_encrypted_tokens_and_details(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    assert row.user_id == "u1" and row.provider == "fake" and row.connection_name == "fake"
    assert row.account_email == "demo@example.com" and row.scopes == "gmail.send openid email"
    assert row.refresh_token_enc and "fake-refresh" not in row.refresh_token_enc
    assert cipher.decrypt(row.refresh_token_enc).startswith("fake-refresh-")
    assert row.expires_at > row.connected_at and row.revoked_at is None


def test_status_connected_then_not(session, cipher, fake, providers):
    assert stat(session).connected is False
    connect(session, cipher, fake, providers)
    st = stat(session)
    assert st.connected and st.email == "demo@example.com" and not st.needs_reconnect
    assert st.scopes == SCOPES and isinstance(st.connected_at, datetime)


def test_one_live_row_per_owner_provider_name(session, cipher, fake, providers):
    first = connect(session, cipher, fake, providers)
    second = connect(session, cipher, fake, providers)
    rows = session.execute(select(Connection).order_by(Connection.connected_at)).scalars().all()
    live = [r for r in rows if r.revoked_at is None]
    assert len(rows) == 2 and live == [second] and first.revoked_at is not None


def test_other_users_rows_are_untouched(session, cipher, fake, providers):
    connect(session, cipher, fake, providers, user="u1")
    connect(session, cipher, fake, providers, user="u2")
    assert stat(session, "u1").connected and stat(session, "u2").connected


def test_shared_connection_has_null_user(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers, shared=True)
    assert row.user_id is None
    assert status(session, user_id=None, provider="fake", connection_model=Connection).connected
    assert not stat(session).connected


def finish_state(session, cipher, providers, state, *, code="mock", nonce=None, **kw):
    """complete() on a hand-made state, with the nonce of that state unless one is given."""
    kw.setdefault("expected_user_id", None)
    return complete(session, state=state, code=code, providers=providers, cipher=cipher, connection_model=Connection,
                    redirect_uri="r", expected_nonce=nonce_of(cipher, state) if nonce is None else nonce, **kw)


def test_complete_without_expected_nonce_or_user_is_a_type_error(session, cipher, fake, providers):
    flow = start_flow(session, user_id="u1", provider_name="fake", provider=fake, scopes=SCOPES, redirect_to="",
                      cipher=cipher, redirect_uri="r")
    common = {"state": flow.state, "code": "mock", "providers": providers, "cipher": cipher,
              "connection_model": Connection, "redirect_uri": "r"}
    with pytest.raises(TypeError):
        complete(session, expected_user_id="u1", **common)
    with pytest.raises(TypeError):
        complete(session, expected_nonce=flow.nonce, **common)
    assert session.execute(select(Connection)).first() is None


def test_complete_rejects_tampered_state(session, cipher, fake, providers):
    with pytest.raises(OAuthError) as err:
        finish_state(session, cipher, providers, "garbage", nonce="x")
    assert err.value.code == "invalid_state"


def test_complete_rejects_expired_state(session, cipher, fake, providers):
    state = encode_state(cipher, sub="u1", provider="fake", connection_name="fake", verifier="v",
                         redirect_to="", now=time.time() - 3600)
    with pytest.raises(OAuthError) as err:
        finish_state(session, cipher, providers, state, nonce="x")
    assert err.value.code == "expired_state"


def test_complete_unknown_provider_and_mismatch(session, cipher, fake, providers):
    state = encode_state(cipher, sub="u1", provider="nope", connection_name="nope", verifier="v", redirect_to="")
    with pytest.raises(OAuthError) as err:
        finish_state(session, cipher, providers, state)
    assert err.value.code == "unknown_provider"
    state = encode_state(cipher, sub="u1", provider="fake", connection_name="fake", verifier="v", redirect_to="")
    with pytest.raises(OAuthError) as err:
        finish_state(session, cipher, providers, state, expected_provider="other")
    assert err.value.code == "provider_mismatch"


def test_complete_expected_user_must_match(session, cipher, fake, providers):
    url = start(session, user_id="u1", provider_name="fake", provider=fake, scopes=SCOPES, redirect_to="",
                cipher=cipher, redirect_uri="r")
    with pytest.raises(OAuthError) as err:
        finish_state(session, cipher, providers, unquote(url.split("state=")[1]), expected_user_id="u2")
    assert err.value.code == "invalid_state"


def test_complete_with_wrong_code_or_no_code(session, cipher, fake, providers):
    url = start(session, user_id="u1", provider_name="fake", provider=fake, scopes=SCOPES, redirect_to="",
                cipher=cipher, redirect_uri="r")
    state = unquote(url.split("state=")[1])
    for code in ("wrong", ""):
        with pytest.raises(OAuthError) as err:
            finish_state(session, cipher, providers, state, code=code)
        assert err.value.code == "invalid_code"
    assert session.execute(select(Connection)).first() is None


def test_complete_state_carries_verifier_to_the_exchange(session, cipher, fake):
    url = start(session, user_id="u1", provider_name="fake", provider=fake, scopes=SCOPES, redirect_to="http://app",
                cipher=cipher, redirect_uri="r")
    payload = decode_state(cipher, unquote(url.split("state=")[1]))
    assert payload.redirect_to == "http://app" and pkce.challenge(payload.verifier) in fake._requested


def test_disconnect_revokes_at_provider_and_marks_row(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    refresh = cipher.decrypt(row.refresh_token_enc)
    count = disconnect(session, user_id="u1", provider_name="fake", connection_model=Connection, provider=fake,
                       cipher=cipher)
    assert count == 1 and row.revoked_at is not None and fake.revoked == [refresh]
    assert not stat(session).connected


def test_disconnect_is_best_effort_when_provider_fails(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)

    def boom(token):
        raise RetryableError("down")

    fake.revoke = boom
    assert disconnect(session, user_id="u1", provider_name="fake", connection_model=Connection, provider=fake,
                      cipher=cipher) == 1
    assert row.revoked_at is not None


def test_disconnect_nothing_returns_zero(session, cipher, fake):
    assert disconnect(session, user_id="u1", provider_name="fake", connection_model=Connection) == 0


def test_access_token_on_revoked_row_requires_reconnect(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    disconnect(session, user_id="u1", provider_name="fake", connection_model=Connection)
    with pytest.raises(ReconnectRequired):
        access_token(session, row, provider=fake, cipher=cipher)


def test_reconnecting_after_failure_gives_a_clean_live_row(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    fake.fail_refresh_with("invalid_grant")
    with pytest.raises(ReconnectRequired):
        access_token(session, row, provider=fake, cipher=cipher)
    fake.fail_refresh_with(None)
    connect(session, cipher, fake, providers)
    assert stat(session).connected and not stat(session).needs_reconnect
