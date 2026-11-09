from datetime import datetime

import httpx
import pytest
from conftest import Connection, connect, stat

import bond_oauth.service as svc
from bond_oauth import GoogleOAuth, ReconnectRequired, RetryableError, TokenCipher, access_token


def test_access_token_refreshes_and_caches(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    first = access_token(session, row, provider=fake, cipher=cipher)
    second = access_token(session, row, provider=fake, cipher=cipher)
    assert first == second and fake.refresh_calls == 1


def test_access_token_cache_expires_after_fifty_minutes(session, cipher, fake, providers, monkeypatch):
    row = connect(session, cipher, fake, providers)
    clock = [1000.0]
    monkeypatch.setattr(svc, "_monotonic", lambda: clock[0])
    access_token(session, row, provider=fake, cipher=cipher)
    clock[0] += 49 * 60
    access_token(session, row, provider=fake, cipher=cipher)
    assert fake.refresh_calls == 1
    clock[0] += 2 * 60
    access_token(session, row, provider=fake, cipher=cipher)
    assert fake.refresh_calls == 2


def test_cache_misses_when_refresh_ciphertext_changes(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    access_token(session, row, provider=fake, cipher=cipher)
    row.refresh_token_enc = cipher.encrypt(cipher.decrypt(row.refresh_token_enc))  # same token, new ciphertext
    access_token(session, row, provider=fake, cipher=cipher)
    assert fake.refresh_calls == 2


def test_refresh_uses_stored_scopes(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers, scopes=["a", "b"])
    seen = []
    original = fake.refresh
    fake.refresh = lambda rt, *, scopes: (seen.append(scopes), original(rt, scopes=scopes))[1]
    access_token(session, row, provider=fake, cipher=cipher)
    assert seen == [["a", "b"]]


def test_mark_true_stores_new_token_and_expiry(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    old_access = row.access_token_enc
    token = access_token(session, row, provider=fake, cipher=cipher)
    assert cipher.decrypt(row.access_token_enc) == token and row.access_token_enc != old_access


def test_mark_false_leaves_row_untouched(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    before = (row.access_token_enc, row.expires_at, row.last_error, row.updated_at)
    access_token(session, row, provider=fake, cipher=cipher, mark=False)
    assert (row.access_token_enc, row.expires_at, row.last_error, row.updated_at) == before


def test_invalid_grant_marks_needs_reconnect_and_fires_hook_once(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    fake.fail_refresh_with("invalid_grant")
    fired = []
    hook = lambda conn, reason: fired.append((conn.id, reason))
    for _ in range(3):
        with pytest.raises(ReconnectRequired):
            access_token(session, row, provider=fake, cipher=cipher, on_reconnect_needed=hook)
    assert fired == [(row.id, "invalid_grant")]
    st = stat(session)
    assert st.connected and st.needs_reconnect and st.last_error == "invalid_grant"


def test_each_reconnect_code_marks(session, cipher, fake, providers):
    for code in ("invalid_grant", "unauthorized_client", "invalid_client"):
        row = connect(session, cipher, fake, providers, user=f"u-{code}")
        fake.fail_refresh_with(code)
        with pytest.raises(ReconnectRequired):
            access_token(session, row, provider=fake, cipher=cipher)
        assert row.last_error == code


def test_http_401_marks_needs_reconnect(session, cipher):
    google = GoogleOAuth("c", "s", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    row = Connection(user_id="u1", provider="google", connection_name="google", account_email="a@example.com",
                     refresh_token_enc=cipher.encrypt("rt"), scopes="x", connected_at=datetime(2026, 1, 1))
    session.add(row)
    session.commit()
    with pytest.raises(ReconnectRequired):
        access_token(session, row, provider=google, cipher=cipher)
    assert row.last_error == "http_401"


def test_mark_false_does_not_write_or_fire_hook_on_failure(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    fake.fail_refresh_with("invalid_grant")
    fired = []
    with pytest.raises(ReconnectRequired):
        access_token(session, row, provider=fake, cipher=cipher, mark=False, on_reconnect_needed=fired.append)
    assert row.last_error is None and fired == []


def test_successful_refresh_clears_last_error(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    fake.fail_refresh_with("invalid_grant")
    with pytest.raises(ReconnectRequired):
        access_token(session, row, provider=fake, cipher=cipher)
    fake.fail_refresh_with(None)
    access_token(session, row, provider=fake, cipher=cipher)
    assert row.last_error is None and not stat(session).needs_reconnect


def test_5xx_and_timeouts_raise_retryable_and_do_not_mark(session, cipher):
    def make(handler):
        return GoogleOAuth("c", "s", httpx.Client(transport=httpx.MockTransport(handler)))

    def boom(request):
        raise httpx.ConnectTimeout("t")

    row = Connection(user_id="u1", provider="google", connection_name="google", account_email="a@example.com",
                     refresh_token_enc=cipher.encrypt("rt"), connected_at=datetime(2026, 1, 1))
    session.add(row)
    session.commit()
    for provider in (make(lambda r: httpx.Response(502)), make(boom)):
        with pytest.raises(RetryableError):
            access_token(session, row, provider=provider, cipher=cipher)
    assert row.last_error is None


def test_other_400_is_retryable_not_a_reconnect(session, cipher):
    google = GoogleOAuth("c", "s", httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": "temporarily_unavailable"}))))
    row = Connection(user_id="u1", provider="google", connection_name="google", account_email="a@example.com",
                     refresh_token_enc=cipher.encrypt("rt"), connected_at=datetime(2026, 1, 1))
    session.add(row)
    session.commit()
    with pytest.raises(RetryableError):
        access_token(session, row, provider=google, cipher=cipher)


def test_undecryptable_refresh_token_needs_reconnect(session, cipher, fake, providers):
    row = connect(session, cipher, fake, providers)
    with pytest.raises(ReconnectRequired):
        access_token(session, row, provider=fake, cipher=TokenCipher("other-key"))
    assert row.last_error == "undecryptable"


