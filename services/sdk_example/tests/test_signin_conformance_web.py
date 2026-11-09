# ruff: noqa: F811
"""Web sign-in through the real stack: happy path, Microsoft full scopes, refusals."""

from __future__ import annotations

from bond_oauth.fake import FAKE_TENANT
from fastapi.testclient import TestClient
from signin_conformance_support import (  # noqa: F401
    ACCESS,
    GOOGLE,
    MICROSOFT,
    ORIGIN,
    REDIRECT,
    REFRESH,
    AuthSession,
    Connection,
    User,
    callback,
    client,
    code_of,
    count,
    reason_of,
    stack,
    web_sign_in,
    web_start,
)
from sqlalchemy import select

# 2. web happy path ---------------------------------------------------------------------------------------------


def _flags(header: str) -> str:
    return header.lower().replace(" ", "")


def test_web_sign_in_end_to_end(stack, client):
    started, state = web_start(client)
    nonce_cookies = [c for c in started.headers.get_list("set-cookie") if c.startswith("bond_signin_")]
    assert len(nonce_cookies) == 1
    flags = _flags(nonce_cookies[0])
    assert "httponly" in flags and "samesite=lax" in flags and "path=/auth/signin" in flags
    assert "max-age=600" in flags

    done = callback(client, GOOGLE, state, "demo.google@example.com")
    assert done.status_code == 302
    assert done.headers["location"] == f"{REDIRECT}?signin=ok"
    cookies = {c.split("=", 1)[0]: _flags(c) for c in done.headers.get_list("set-cookie")}
    assert "httponly" in cookies[ACCESS] and "samesite=lax" in cookies[ACCESS] and "path=/;" in cookies[ACCESS] + ";"
    assert "httponly" in cookies[REFRESH] and "samesite=lax" in cookies[REFRESH] and "path=/auth" in cookies[REFRESH]
    assert "path=/auth/signin" not in cookies[REFRESH]
    assert any(k.startswith("bond_signin_") and "max-age=0" in v for k, v in cookies.items())  # nonce cleared
    assert "refresh_token" not in done.headers["location"]

    me = client.get("/auth/me")  # the access cookie alone
    assert me.status_code == 200 and me.json()["id"] == "u-google"

    old_refresh = client.cookies.get(REFRESH)
    old_access = client.cookies.get(ACCESS)
    refreshed = client.post("/auth/refresh", json={}, headers=ORIGIN)
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["token"] and body["user"]["id"] == "u-google" and "refresh_token" not in body
    assert client.cookies.get(REFRESH) and client.cookies.get(REFRESH) != old_refresh
    assert client.cookies.get(ACCESS) != old_access or body["token"] != old_access

    out = client.post("/auth/logout", json={}, headers=ORIGIN)
    assert out.status_code == 200 and out.json() == {"status": "logged_out"}
    cleared = out.headers.get_list("set-cookie")
    assert any(c.startswith(ACCESS) and "max-age=0" in _flags(c) for c in cleared)
    assert any(c.startswith(REFRESH) and "max-age=0" in _flags(c) for c in cleared)
    assert client.cookies.get(ACCESS) is None and client.cookies.get(REFRESH) is None

    assert count(stack, Connection) == 0  # identity-only: no connection row
    assert stack.directory.sign_ins == [("u-google", GOOGLE, True)]
    assert "signin_start" in stack.rate_calls and "signin_callback" in stack.rate_calls
    assert "refresh" in stack.rate_calls


def test_logout_ends_the_family(stack, client):
    web_sign_in(client)
    token = client.cookies.get(REFRESH)
    client.post("/auth/logout", json={}, headers=ORIGIN)
    again = client.post("/auth/refresh", json={"refresh_token": token}, headers=ORIGIN)
    assert again.status_code == 401 and code_of(again) in ("refresh_revoked", "refresh_reused")


def test_second_web_sign_in_is_not_first(stack, client):
    web_sign_in(client)
    web_sign_in(client)
    assert [first for *_rest, first in stack.directory.sign_ins] == [True, False]
    with stack.db() as s:
        user = s.get(User, "u-google")
        assert user.identity[0] == GOOGLE and user.identity[1].startswith("fake-")


# 3. Microsoft full scopes --------------------------------------------------------------------------------------


def test_microsoft_full_scopes_store_one_connection(stack, client):
    done = web_sign_in(client, MICROSOFT, "demo.microsoft@example.com")
    assert done.headers["location"] == f"{REDIRECT}?signin=ok"
    with stack.db() as s:
        rows = s.scalars(select(Connection)).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.user_id == "u-ms" and row.provider == MICROSOFT and row.revoked_at is None
        assert row.account_email == "demo.microsoft@example.com"
        assert "offline_access" in (row.scopes or "")
        assert stack.cipher.decrypt(row.refresh_token_enc).startswith("fake-refresh-")
        assert s.get(User, "u-ms").identity[1].startswith(f"{FAKE_TENANT}:")
    web_sign_in(client, MICROSOFT, "demo.microsoft@example.com")  # again: still one live row
    with stack.db() as s:
        live = s.scalars(select(Connection).where(Connection.revoked_at.is_(None))).all()
        assert len(live) == 1


def test_microsoft_wrong_tenant_is_refused(stack, client):
    stack.microsoft.pinned_tenant = "11111111-2222-4333-8444-555555555555"
    done = web_sign_in(client, MICROSOFT, "demo.microsoft@example.com")
    assert done.status_code == 302 and reason_of(done) == "tenant_mismatch"
    assert "signin=error" in done.headers["location"]
    assert count(stack, Connection) == 0 and count(stack, AuthSession) == 0
    assert client.cookies.get(ACCESS) is None and client.cookies.get(REFRESH) is None


# 4. refusals through the real stack ----------------------------------------------------------------------------


def test_uninvited_email_is_refused_and_recorded(stack, client):
    done = web_sign_in(client, GOOGLE, "stranger@example.com")
    assert reason_of(done) == "not_invited"
    assert count(stack, Connection) == 0 and count(stack, AuthSession) == 0
    assert stack.directory.refusals == [("not_invited", "stranger@example.com", GOOGLE)]
    assert client.get("/auth/me").json()["detail"]["code"] == "invalid_token"


def test_deactivated_user_is_refused(stack, client):
    done = web_sign_in(client, GOOGLE, "off@example.com")
    assert reason_of(done) == "deactivated"
    assert count(stack, AuthSession) == 0
    assert stack.directory.refusals[0][0] == "deactivated"


def test_consent_declined_redirects_without_a_row(stack, client):
    _, state = web_start(client)
    done = client.get(f"/auth/signin/{GOOGLE}/callback", params={"state": state, "error": "access_denied"})
    assert reason_of(done) == "consent_declined" and count(stack, AuthSession) == 0


def test_attacker_link_without_the_matching_cookie_is_400(stack):
    victim = TestClient(stack.app, follow_redirects=False)
    attacker = TestClient(stack.app, follow_redirects=False)
    _, state = web_start(attacker)  # the attacker starts a flow and hands the callback link to the victim
    done = callback(victim, GOOGLE, state, "demo.google@example.com")
    assert done.status_code == 400 and code_of(done) == "invalid_state"
    assert "location" not in done.headers
    assert count(stack, AuthSession) == 0 and stack.directory.sign_ins == []


def test_start_needs_an_allowed_origin(client):
    body = {"redirect_to": REDIRECT, "mode": "web"}
    assert client.post(f"/auth/signin/{GOOGLE}/start", json=body).status_code == 403
    foreign = client.post(f"/auth/signin/{GOOGLE}/start", json=body, headers={"Origin": "https://evil.example.org"})
    assert foreign.status_code == 403 and code_of(foreign) == "invalid_origin"
    assert client.post("/auth/signin/nope/start", json=body, headers=ORIGIN).status_code == 404


def _state_made_at(stack, state: str, issued_at: float) -> str:
    """The same sign-in state (same nonce, verifier, binding) re-sealed as if it had been issued at ``issued_at``."""
    from bond_oauth import decode_state, encode_state

    p = decode_state(stack.cipher, state)
    return encode_state(stack.cipher, sub=None, provider=p.provider, connection_name=p.connection_name,
                        verifier=p.verifier, redirect_to=p.redirect_to, native=False, intent="signin",
                        oidc_nonce=p.oidc_nonce, nonce=p.nonce, now=issued_at)


def _nonce_cookie_name(stack, state: str) -> str:
    import hashlib

    from bond_oauth import decode_state

    return "bond_signin_" + hashlib.sha256(decode_state(stack.cipher, state).nonce.encode()).hexdigest()[:8]


def test_expired_state_with_the_right_cookie_redirects_with_signin_expired(stack, client):
    import time

    _, state = web_start(client)
    old = _state_made_at(stack, state, time.time() - 700)
    done = callback(client, GOOGLE, old, "demo.google@example.com")
    assert done.status_code == 302 and reason_of(done) == "signin_expired"
    assert "signin=error" in done.headers["location"] and done.headers["location"].startswith(REDIRECT)
    assert count(stack, AuthSession) == 0 and stack.directory.sign_ins == []


def test_expired_state_without_the_cookie_is_still_400(stack):
    import time

    _, state = web_start(TestClient(stack.app, follow_redirects=False))
    done = callback(TestClient(stack.app, follow_redirects=False), GOOGLE,
                    _state_made_at(stack, state, time.time() - 700), "demo.google@example.com")
    assert done.status_code == 400 and code_of(done) == "invalid_state"


def test_state_used_at_another_providers_callback_is_400(stack, client):
    _, state = web_start(client, GOOGLE)
    done = callback(client, MICROSOFT, state, "demo.microsoft@example.com")
    assert done.status_code == 400 and code_of(done) == "invalid_state"
    assert count(stack, AuthSession) == 0 and count(stack, Connection) == 0


def test_invalid_state_clears_the_per_flow_nonce_cookie(stack):
    attacker = TestClient(stack.app, follow_redirects=False)
    _, state = web_start(attacker)
    name = _nonce_cookie_name(stack, state)
    done = callback(TestClient(stack.app, follow_redirects=False), GOOGLE, state, "demo.google@example.com")
    assert done.status_code == 400
    cleared = [c for c in done.headers.get_list("set-cookie") if c.startswith(name)]
    assert cleared and "max-age=0" in _flags(cleared[0]) and "path=/auth/signin" in _flags(cleared[0])
