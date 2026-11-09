"""Native (phone) sign-in through the real example app: the app is the PKCE client of OUR server. It sends the
sha256 of a device secret at start and presents the secret at redeem; the code in the return link is useless
without it. Tokens never ride in a URL."""

import hashlib

from signin_util import GOOGLE, MICROSOFT, RETURN, browser, consent, query_of, rows, state_in

from sdk_example.models.connections import OAuthConnection
from sdk_example.models.sessions import AuthSession

SECRET = "device-secret-0123456789abcdef"
CHALLENGE = hashlib.sha256(SECRET.encode()).hexdigest()


def start_native(client, provider=GOOGLE, *, attempt="att-1", challenge=CHALLENGE, redirect_to=None):
    body = {"mode": "native", "device_challenge": challenge, "attempt": attempt,
            "redirect_to": redirect_to or f"{RETURN}/{provider}"}
    reply = client.post(f"/auth/signin/{provider}/start", json=body)  # no Origin, no cookie: not a browser
    assert reply.status_code == 200, reply.text
    assert not reply.headers.get_list("set-cookie")  # the device secret binds it, not a cookie
    return state_in(reply.json()["url"])


def system_browser_returns(app, state, email="demo@example.com"):
    """The system browser (a fresh client) finishes consent; the callback sends it to the app's return link."""
    return consent(browser(app), state, email)


def redeem(client, code, secret=SECRET):
    return client.post("/auth/signin/redeem", json={"code": code, "device_secret": secret})


def test_native_round_trip_gives_tokens_in_the_body_only(app):
    phone = browser(app)
    back = system_browser_returns(app, start_native(phone))
    params = query_of(back)
    assert back.status_code == 302 and back.headers["location"].startswith(f"{RETURN}/{GOOGLE}?")
    assert set(params) == {"attempt", "code"} and params["attempt"] == "att-1"
    assert not back.headers.get_list("set-cookie")
    done = redeem(phone, params["code"])
    assert done.status_code == 200 and not done.headers.get_list("set-cookie")
    body = done.json()
    assert body["token"] and body["refresh_token"] and body["user"]["email"] == "demo@example.com"
    assert phone.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 200
    rotated = phone.post("/auth/refresh", json={"refresh_token": body["refresh_token"], "rotation_id": "rot-1"})
    assert rotated.status_code == 200 and rotated.json()["refresh_token"] != body["refresh_token"]
    assert not rotated.headers.get_list("set-cookie")  # a bearer-style refresh needs no Origin and sets no cookie
    assert {r.provider for r in rows(app, AuthSession)} == {GOOGLE}


def test_a_wrong_device_secret_burns_the_code(app):
    phone = browser(app)
    code = query_of(system_browser_returns(app, start_native(phone)))["code"]
    wrong = redeem(phone, code, secret="someone-elses-secret")
    assert wrong.status_code == 401 and wrong.json()["detail"]["code"] == "invalid_handoff"
    assert redeem(phone, code).status_code == 401  # the thief spent it; the real phone must start again
    assert rows(app, AuthSession) == []


def test_a_code_redeems_once(app):
    phone = browser(app)
    code = query_of(system_browser_returns(app, start_native(phone)))["code"]
    assert redeem(phone, code).status_code == 200
    again = redeem(phone, code)
    assert again.status_code == 401 and again.json()["detail"]["code"] == "invalid_handoff"
    assert len(rows(app, AuthSession)) == 1


def test_a_refusal_comes_back_as_an_error_not_a_code(app):
    phone = browser(app)
    back = system_browser_returns(app, start_native(phone), "uninvited@example.com")
    assert query_of(back) == {"attempt": "att-1", "error": "not_invited"}
    assert rows(app, AuthSession) == []


def test_a_native_start_is_validated(app):
    phone = browser(app)
    for body in ({"device_challenge": "short", "attempt": "a"},
                 {"device_challenge": CHALLENGE, "attempt": "not valid!"},
                 {"device_challenge": CHALLENGE, "attempt": "a", "redirect_to": "https://evil.example/app/return/x"},
                 {"attempt": "a"}):
        reply = phone.post(f"/auth/signin/{GOOGLE}/start",
                           json={"mode": "native", "redirect_to": f"{RETURN}/{GOOGLE}", **body})
        assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_request", body


def test_the_custom_scheme_fallback_is_allowed_by_name_only(app):
    phone = browser(app)
    scheme = "org.example.sdkdemo://signin"
    assert start_native(phone, redirect_to=scheme)
    reply = phone.post(f"/auth/signin/{GOOGLE}/start", json={
        "mode": "native", "device_challenge": CHALLENGE, "attempt": "a", "redirect_to": "other.scheme://signin"})
    assert reply.status_code == 400


def test_microsoft_native_stores_the_connection_under_the_identified_user_at_the_callback(app):
    phone = browser(app)
    back = system_browser_returns(app, start_native(phone, MICROSOFT), "demo.microsoft@example.com")
    assert "code" in query_of(back)
    live = rows(app, OAuthConnection, revoked_at=None)  # stored before redeem: the identity is already proven
    assert [r.provider for r in live] == [MICROSOFT]
    assert redeem(phone, query_of(back)["code"]).status_code == 200
