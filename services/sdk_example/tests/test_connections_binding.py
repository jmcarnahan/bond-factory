"""The flow is bound to the browser that started it: session cookie (who) plus nonce cookie (which flow)."""

import time
from types import SimpleNamespace

from bond_oauth import encode_state
from bond_oauth import state as state_module
from connections_util import APP, NONCE, begin, headers, live_rows, start, state_of, statuses
from fastapi.testclient import TestClient

from sdk_example.models.auth import DEMO_USER_ID, VIEWER_USER_ID

GOOGLE = "/connections/fake-google"


def callback(client, state, **kw):
    return client.get(f"{GOOGLE}/callback", params={"state": state, "code": "mock"}, follow_redirects=False, **kw)


def test_browser_flow_needs_only_the_session_cookie(client):
    """After the authed XHR start, /go, the consent page and the callback carry no bearer header at all."""
    h = headers(client)
    go = client.get(start(client, h), follow_redirects=False)
    assert go.status_code == 302
    state = state_of(go.headers["location"])
    assert client.get("/connections/fake/consent", params={"state": state}).status_code == 200
    reply = callback(client, state)
    assert reply.status_code == 302 and "connection=connected" in reply.headers["location"]
    assert statuses(client, h)["fake-google"]["connected"]


def test_go_sets_a_bound_nonce_cookie_and_redirects_to_consent(client):
    h = headers(client)
    go = client.get(start(client, h), follow_redirects=False)
    cookie = go.headers["set-cookie"].lower()
    assert go.status_code == 302
    assert go.headers["location"].startswith("http://testserver/connections/fake/consent?state=")
    assert NONCE in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "max-age=600" in cookie and "path=/connections" in cookie and "secure" not in cookie


def test_go_without_a_session_is_401_and_sets_no_cookie(app, client):
    url = start(client, headers(client))
    reply = TestClient(app).get(url, follow_redirects=False)
    assert reply.status_code == 401 and reply.json()["detail"]["code"] == "invalid_token"
    assert "set-cookie" not in reply.headers


def test_go_with_another_users_state_is_403_and_sets_no_cookie(app, client):
    """The attack: an attacker starts a flow and sends the victim the /go link."""
    attacker_url = start(client, headers(client))  # demo-user-1 starts a flow
    victim = TestClient(app)
    victim_headers = headers(victim, VIEWER_USER_ID)  # the victim's own session cookie
    for kwargs in ({}, {"headers": victim_headers}):
        reply = victim.get(attacker_url, follow_redirects=False, **kwargs)
        assert reply.status_code == 403 and reply.json()["detail"]["code"] == "forbidden"
        assert "set-cookie" not in reply.headers


def test_go_with_a_bad_state_or_provider_mismatch_is_400(client):
    h = headers(client)
    assert client.get(f"{GOOGLE}/go", params={"state": "junk"}, headers=h).status_code == 400
    state = state_of(start(client, h))
    mismatch = client.get("/connections/fake-microsoft/go", params={"state": state}, headers=h)
    assert mismatch.status_code == 400 and mismatch.json()["detail"]["code"] == "provider_mismatch"


def test_callback_without_a_session_is_401_and_stores_nothing(app, client):
    h = headers(client)
    state = begin(client, h)
    reply = callback(TestClient(app), state)
    assert reply.status_code == 401 and "location" not in reply.headers
    assert live_rows(app) == 0


def test_callback_with_a_session_but_no_nonce_cookie_is_400(app, client):
    h = headers(client)
    state = state_of(start(client, h))  # /go never visited in this browser
    reply = callback(client, state, headers=h)
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_state"
    assert "location" not in reply.headers and live_rows(app) == 0


def test_cookie_from_one_flow_with_the_state_of_another_is_refused(app, client):
    h = headers(client)
    begin(client, h)  # flow A: the cookie holds A's nonce
    state_b = state_of(start(client, h))  # flow B minted but not opened here
    reply = callback(client, state_b, headers=h)
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_state"
    assert live_rows(app) == 0


def test_forged_cookie_value_is_refused(app, client):
    h = headers(client)
    state = begin(client, h)
    other_browser = TestClient(app)
    other = headers(other_browser)
    reply = callback(other_browser, state, headers={**other, "cookie": f"{NONCE}=forged"})
    assert reply.status_code == 400 and live_rows(app) == 0


def test_another_session_with_the_right_nonce_is_refused(app, client):
    """Even with the victim holding the attacker's nonce cookie, a different session user cannot complete."""
    h = headers(client)
    state = begin(client, h)
    victim = TestClient(app)
    victim_headers = headers(victim, VIEWER_USER_ID)
    nonce = client.cookies.get(NONCE)
    assert nonce
    reply = callback(victim, state, headers={**victim_headers, "cookie": f"{NONCE}={nonce}"})
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_state"
    assert live_rows(app) == 0


def test_refused_callback_clears_the_nonce_cookie(client):
    h = headers(client)
    state = state_of(start(client, h))
    reply = callback(client, state, headers=h)
    assert "max-age=0" in reply.headers["set-cookie"].lower()


def test_successful_callback_clears_the_nonce_cookie(client):
    h = headers(client)
    state = begin(client, h)
    reply = callback(client, state, headers=h)
    assert reply.status_code == 302 and "max-age=0" in reply.headers["set-cookie"].lower()
    assert client.cookies.get(NONCE) is None


def test_callback_with_a_bad_state_is_400_not_a_redirect(client):
    reply = callback(client, "junk", headers=headers(client))
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_state"


def test_callback_provider_must_match_state(client):
    h = headers(client)
    state = begin(client, h)
    reply = client.get("/connections/fake-microsoft/callback", params={"state": state, "code": "mock"}, headers=h,
                       follow_redirects=False)
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "provider_mismatch"


def _minted(app, at):
    """A state for demo-user-1 minted at epoch second ``at`` (so it expires at ``at + 600``)."""
    wiring = app.state.oauth
    return encode_state(wiring.cipher, sub=DEMO_USER_ID, provider="fake-google", connection_name="fake-google",
                        verifier="v", redirect_to=APP, now=at)


def _clock_at(monkeypatch, now):
    monkeypatch.setattr(state_module, "time", SimpleNamespace(time=lambda: now))


def test_expired_state_at_the_callback_is_400_expired_state(app, client):
    h = headers(client)
    state = _minted(app, time.time() - 3600)
    reply = callback(client, state, headers=h)
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "expired_state"
    assert "location" not in reply.headers and live_rows(app) == 0


def test_state_is_expired_exactly_at_exp_but_not_a_moment_before(app, client, monkeypatch):
    """Boundary: expired AT exp (like a JWT). Just before, the state passes and the missing nonce cookie answers."""
    h = headers(client)
    start_at = time.time()
    state = _minted(app, start_at)
    _clock_at(monkeypatch, start_at + 600)
    at_exp = callback(client, state, headers=h)
    assert at_exp.status_code == 400 and at_exp.json()["detail"]["code"] == "expired_state"
    _clock_at(monkeypatch, start_at + 600 - 0.001)
    before = callback(client, state, headers=h)
    assert before.status_code == 400 and before.json()["detail"]["code"] == "invalid_state"


def test_expired_state_at_go_is_400_expired_state(app, client):
    h = headers(client)
    reply = client.get(f"{GOOGLE}/go", params={"state": _minted(app, time.time() - 3600)}, headers=h)
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "expired_state"


def test_redirect_target_is_the_allowlisted_app_page(client):
    h = headers(client)
    reply = callback(client, begin(client, h), headers=h)
    assert reply.headers["location"].startswith(APP + "?")
