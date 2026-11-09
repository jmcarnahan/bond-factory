"""The phone-app flow: system browser without cookies, then a one-time code redeemed with the bearer token."""

from urllib.parse import parse_qs, urlsplit

from connections_util import headers, live_rows, state_of, statuses
from fastapi.testclient import TestClient
from tasks_util import grant

from sdk_example.models.auth import VIEWER_USER_ID

NATIVE = "sdkdemo://connections"
GOOGLE = "/connections/fake-google"


def start_native(client, h, redirect_to=NATIVE, **params):
    return client.get(f"{GOOGLE}/start", params={"mode": "native", "redirect_to": redirect_to, **params}, headers=h)


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


def test_whole_native_round_trip_without_cookies(app, client):
    h = headers(client)
    url = start_native(client, h).json()["url"]
    _, reply = system_browser(app, url)
    params = returned(reply)
    assert params["connection"] == "connected" and params["provider"] == "fake-google" and params["code"]
    assert live_rows(app) == 0  # the callback alone stores nothing
    app_client = TestClient(app)  # the phone app: bearer token only
    token_only = {"Authorization": h["Authorization"]}
    done = app_client.post(f"{GOOGLE}/redeem", json={"code": params["code"]}, headers=token_only)
    assert done.status_code == 200 and done.json()["connected"] is True and live_rows(app) == 1
    assert statuses(client, h)["fake-google"]["connected"]


def test_redeem_by_another_user_is_refused(app, client):
    h = headers(client)
    code = returned(system_browser(app, start_native(client, h).json()["url"])[1])["code"]
    other = TestClient(app)
    grant(app, VIEWER_USER_ID, "connections.manage")
    reply = other.post(f"{GOOGLE}/redeem", json={"code": code}, headers=headers(other, VIEWER_USER_ID))
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_handoff"
    assert live_rows(app) == 0  # nothing was stored for anyone
    assert client.post(f"{GOOGLE}/redeem", json={"code": code}, headers=h).status_code == 200  # owner still can


def test_redeem_at_the_wrong_provider_is_refused_and_stores_nothing(app, client):
    h = headers(client)
    code = returned(system_browser(app, start_native(client, h).json()["url"])[1])["code"]
    wrong = client.post("/connections/fake-microsoft/redeem", json={"code": code}, headers=h)
    assert wrong.status_code == 400 and wrong.json()["detail"]["code"] == "invalid_handoff"
    assert live_rows(app) == 0
    assert client.post(f"{GOOGLE}/redeem", json={"code": code}, headers=h).status_code == 200
    assert live_rows(app) == 1


def test_replay_is_refused(app, client):
    h = headers(client)
    code = returned(system_browser(app, start_native(client, h).json()["url"])[1])["code"]
    assert client.post(f"{GOOGLE}/redeem", json={"code": code}, headers=h).status_code == 200
    again = client.post(f"{GOOGLE}/redeem", json={"code": code}, headers=h)
    assert again.status_code == 400 and again.json()["detail"]["code"] == "invalid_handoff"
    assert live_rows(app) == 1


def test_redeem_needs_a_session_and_a_real_code(app, client):
    assert TestClient(app).post(f"{GOOGLE}/redeem", json={"code": "x"}).status_code == 401
    bad = client.post(f"{GOOGLE}/redeem", json={"code": "garbage"}, headers=headers(client))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_handoff"


def test_native_redirect_must_be_on_the_allowlist(client):
    h = headers(client)
    for target in ("evil://connections", "sdkdemo://other", "http://localhost:8078/connections"):
        reply = start_native(client, h, redirect_to=target)
        assert reply.status_code == 400 and reply.json()["detail"]["code"] == "redirect_not_allowed", target
    assert start_native(client, h, redirect_to=NATIVE + "?x=1").status_code == 200
    assert client.get(f"{GOOGLE}/start", params={"mode": "native"}, headers=h).status_code == 200  # default entry


def test_native_start_needs_the_capability(app):
    viewer = TestClient(app)
    reply = start_native(viewer, headers(viewer, VIEWER_USER_ID))
    assert reply.status_code == 403


def test_native_error_redirects_to_the_app_without_a_code(app, client):
    url = start_native(client, headers(client)).json()["url"]
    browser = TestClient(app)
    state = state_of(browser.get(url, follow_redirects=False).headers["location"])
    reply = browser.get(f"{GOOGLE}/callback", params={"state": state, "error": "access_denied"},
                        follow_redirects=False)
    params = returned(reply)
    assert params == {"connection": "error", "provider": "fake-google", "reason": "access_denied"}
    assert live_rows(app) == 0


def test_web_state_still_needs_the_session_and_nonce(app, client):
    """A web state is not turned native by the new route code: /go and the callback still refuse cookie-less use."""
    h = headers(client)
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
