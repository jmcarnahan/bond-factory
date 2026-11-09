"""The phone-app connect flow: system browser without cookies, then a one-time code redeemed with the bearer token
AND the device secret (the sha256 of which rode in the state). A wrong secret, user or provider burns the code."""

import hashlib
from urllib.parse import parse_qs, urlsplit

from connections_util import headers, live_rows, state_of, statuses
from fastapi.testclient import TestClient
from tasks_util import grant

from sdk_example.models.auth import VIEWER_USER_ID, User

NATIVE = "sdkdemo://connections"
GOOGLE = "/connections/fake-google"
SECRET = "phone-secret-0123456789abcdef"
CHALLENGE = hashlib.sha256(SECRET.encode()).hexdigest()


def bound_headers(app, client):
    """The demo user signed in WITH fake-google: a phone connect is only allowed for an account bound by sign-in.
    The subject is what the fake provider derives for the address the plain `mock` code stands for."""
    h = headers(client)
    subject = "fake-" + hashlib.sha1(b"demo.google@example.com").hexdigest()[:12]
    with app.state.session_factory() as session:
        row = session.get(User, "demo-user-1")
        row.identity_provider, row.identity_subject = "fake-google", subject
        session.commit()
    return h


def start_native(client, h, redirect_to=NATIVE, challenge=CHALLENGE, **params):
    query = {"mode": "native", "redirect_to": redirect_to, "attempt": "att-0",
             **({"device_challenge": challenge} if challenge else {}), **params}
    return client.get(f"{GOOGLE}/start", params=query, headers=h)


def system_browser(app, go_url):
    """A fresh client with no cookies and no headers: go -> consent -> callback. Returns (state, callback response)."""
    browser = TestClient(app)
    go = browser.get(go_url, follow_redirects=False)
    assert go.status_code == 302 and "set-cookie" not in go.headers
    state = state_of(go.headers["location"])
    assert browser.get("/connections/fake/consent", params={"state": state}).status_code == 200
    reply = browser.get(f"{GOOGLE}/callback", params={"state": state, "code": "mock"}, follow_redirects=False)
    assert "set-cookie" not in reply.headers
    return state, reply


def returned(reply):
    assert reply.status_code == 302
    location = reply.headers["location"]
    assert location.startswith(NATIVE + "?")
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


def redeem(client, h, code, secret=SECRET, provider="fake-google"):
    return client.post(f"/connections/{provider}/redeem", json={"code": code, "device_secret": secret}, headers=h)


def code_from(app, client, h, **params):
    return returned(system_browser(app, start_native(client, h, **params).json()["url"])[1])["code"]


def assert_invalid_handoff(reply):
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_handoff"


def test_whole_native_round_trip_without_cookies(app, client):
    h = bound_headers(app, client)
    url = start_native(client, h, attempt="try-1").json()["url"]
    _, reply = system_browser(app, url)
    params = returned(reply)
    assert params["connection"] == "connected" and params["provider"] == "fake-google" and params["code"]
    assert params["attempt"] == "try-1"  # echoed, opaque
    assert live_rows(app) == 0  # the callback alone stores nothing
    app_client = TestClient(app)  # the phone app: bearer token only
    done = redeem(app_client, {"Authorization": h["Authorization"]}, params["code"])
    assert done.status_code == 200 and done.json()["connected"] is True and live_rows(app) == 1
    assert statuses(client, h)["fake-google"]["connected"]


def test_a_wrong_device_secret_burns_the_code(app, client):
    h = bound_headers(app, client)
    code = code_from(app, client, h)
    assert_invalid_handoff(redeem(client, h, code, secret="not-the-phones-secret"))
    assert_invalid_handoff(redeem(client, h, code))  # the right secret is too late: the code is spent
    assert live_rows(app) == 0


def test_redeem_by_another_user_is_refused_and_burns_the_code(app, client):
    h = bound_headers(app, client)
    code = code_from(app, client, h)
    other = TestClient(app)
    grant(app, VIEWER_USER_ID, "connections.manage")
    assert_invalid_handoff(redeem(other, headers(other, VIEWER_USER_ID), code))
    assert live_rows(app) == 0  # nothing was stored for anyone
    assert_invalid_handoff(redeem(client, h, code))  # a victim lured through an attacker's link gains nothing


def test_redeem_at_the_wrong_provider_is_refused_and_stores_nothing(app, client):
    h = bound_headers(app, client)
    code = code_from(app, client, h)
    assert_invalid_handoff(redeem(client, h, code, provider="fake-microsoft"))
    assert live_rows(app) == 0


def test_replay_is_refused(app, client):
    h = bound_headers(app, client)
    code = code_from(app, client, h)
    assert redeem(client, h, code).status_code == 200
    assert_invalid_handoff(redeem(client, h, code))
    assert live_rows(app) == 1


def test_redeem_needs_a_session_and_a_real_code(app, client):
    assert TestClient(app).post(f"{GOOGLE}/redeem", json={"code": "x", "device_secret": SECRET}).status_code == 401
    assert_invalid_handoff(redeem(client, bound_headers(app, client), "garbage"))


def test_native_redirect_must_be_on_the_allowlist(app, client):
    h = bound_headers(app, client)
    for target in ("evil://connections", "sdkdemo://other", "http://localhost:8078/connections"):
        reply = start_native(client, h, redirect_to=target)
        assert reply.status_code == 400 and reply.json()["detail"]["code"] == "redirect_not_allowed", target
    assert start_native(client, h, redirect_to=NATIVE + "?x=1").status_code == 200
    assert client.get(f"{GOOGLE}/start", params={"mode": "native", "device_challenge": CHALLENGE, "attempt": "a"},
                      headers=h).status_code == 200  # default entry


def test_native_start_needs_a_device_challenge(app, client):
    h = bound_headers(app, client)
    for bad in (None, "short", "G" * 64, SECRET):
        reply = start_native(client, h, challenge=bad)
        assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_request", bad
    assert start_native(client, h, attempt="bad attempt!").status_code == 400
    no_attempt = client.get(f"{GOOGLE}/start", params={"mode": "native", "device_challenge": CHALLENGE}, headers=h)
    assert no_attempt.status_code == 400 and no_attempt.json()["detail"]["code"] == "invalid_request"


def test_native_start_needs_the_capability(app):
    viewer = TestClient(app)
    reply = start_native(viewer, headers(viewer, VIEWER_USER_ID))
    assert reply.status_code == 403


def test_native_error_redirects_to_the_app_without_a_code(app, client):
    url = start_native(client, bound_headers(app, client)).json()["url"]
    browser = TestClient(app)
    state = state_of(browser.get(url, follow_redirects=False).headers["location"])
    reply = browser.get(f"{GOOGLE}/callback", params={"state": state, "error": "access_denied"},
                        follow_redirects=False)
    params = returned(reply)
    assert params == {"connection": "error", "provider": "fake-google", "reason": "consent_declined", "attempt": "att-0"}
    assert live_rows(app) == 0


def test_web_state_still_needs_the_session_and_nonce(app, client):
    """A web state is not turned native by the new route code: /go and the callback still refuse cookie-less use."""
    h = bound_headers(app, client)
    web_url = client.get(f"{GOOGLE}/start", params={"redirect_to": "http://localhost:8078/connections"},
                         headers=h).json()["url"]
    assert TestClient(app).get(web_url, follow_redirects=False).status_code == 401
    state = state_of(web_url)
    reply = TestClient(app).get(f"{GOOGLE}/callback", params={"state": state, "code": "mock"}, follow_redirects=False)
    assert reply.status_code == 401
    assert live_rows(app) == 0


def test_native_mode_with_an_unknown_value_is_400(client):
    reply = client.get(f"{GOOGLE}/start", params={"mode": "tv"}, headers=headers(client))
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_mode"


def test_the_https_app_link_and_a_signin_scheme_are_accepted_like_sign_in(app, client):
    h = bound_headers(app, client)
    for target in ("http://testserver/app/return/fake-google", "org.example.sdkdemo://connections"):
        assert start_native(client, h, redirect_to=target).status_code == 200, target
    other = start_native(client, h, redirect_to="http://testserver/app/return/fake-microsoft")
    assert other.status_code == 400  # the return link names the provider
