# ruff: noqa: F811
"""Native sign-in through the real stack: hand-off, device binding, redeem."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from bond_auth_py import decode_claims
from signin_conformance_support import (  # noqa: F401
    GOOGLE,
    NATIVE_RETURN,
    AuthSession,
    callback,
    client,
    code_of,
    count,
    device_pair,
    native_sign_in,
    native_start,
    stack,
)

# 5. native -----------------------------------------------------------------------------------------------------


def test_native_hand_off_and_redeem(stack, client):
    secret, cb = native_sign_in(client)
    assert cb.status_code == 302
    loc = urlsplit(cb.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == f"{NATIVE_RETURN}/{GOOGLE}"
    query = parse_qs(loc.query)
    assert query["attempt"] == ["att-1"] and query["code"][0]
    assert not cb.headers.get_list("set-cookie")  # native: no browser cookies at all
    assert "token" not in loc.query

    got = client.post("/auth/signin/redeem", json={"code": query["code"][0], "device_secret": secret})
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["token"] and body["refresh_token"] and body["user"]["id"] == "u-google"
    assert not got.headers.get_list("set-cookie")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).json()["id"] == "u-google"

    again = client.post("/auth/signin/redeem", json={"code": query["code"][0], "device_secret": secret})
    assert again.status_code == 401 and code_of(again) == "invalid_handoff"


def test_native_wrong_secret_burns_the_code(stack, client):
    secret, cb = native_sign_in(client)
    code = parse_qs(urlsplit(cb.headers["location"]).query)["code"][0]
    wrong = client.post("/auth/signin/redeem", json={"code": code, "device_secret": "not-the-secret"})
    assert wrong.status_code == 401 and code_of(wrong) == "invalid_handoff"
    right = client.post("/auth/signin/redeem", json={"code": code, "device_secret": secret})
    assert right.status_code == 401 and code_of(right) == "invalid_handoff"
    assert count(stack, AuthSession) == 0


def test_native_refusal_returns_error_to_the_app(stack, client):
    _, cb = native_sign_in(client, email="stranger@example.com")
    query = parse_qs(urlsplit(cb.headers["location"]).query)
    assert query["attempt"] == ["att-1"] and query["error"] == ["not_invited"] and "code" not in query


def test_native_start_validates_device_and_return(client):
    _, challenge = device_pair()
    base = {"mode": "native", "device_challenge": challenge, "attempt": "a-1",
            "redirect_to": f"{NATIVE_RETURN}/{GOOGLE}"}
    assert client.post(f"/auth/signin/{GOOGLE}/start", json=base).status_code == 200
    for patch in ({"device_challenge": "short"}, {"attempt": "bad attempt!"}, {"redirect_to": "https://evil.example.org/"}):
        r = client.post(f"/auth/signin/{GOOGLE}/start", json={**base, **patch})
        assert r.status_code == 400 and code_of(r) == "invalid_request", patch


def test_native_attacker_state_replayed_with_another_device_is_unusable(stack, client):
    """A state started for device A cannot be redeemed by device B: redeem binds the secret."""
    secret_a, challenge_a = device_pair("secret-of-device-a-0123456")
    secret_b, _ = device_pair("secret-of-device-b-0123456")
    cb = callback(client, GOOGLE, native_start(client, challenge_a), "demo.google@example.com")
    code = parse_qs(urlsplit(cb.headers["location"]).query)["code"][0]
    stolen = client.post("/auth/signin/redeem", json={"code": code, "device_secret": secret_b})
    assert stolen.status_code == 401 and code_of(stolen) == "invalid_handoff"
    assert secret_a != secret_b


def test_redeem_carries_the_filled_name(stack, client):
    stack.add_user("u-dora", "dora.example@example.com", name="")
    secret, cb = native_sign_in(client, email="dora.example@example.com")
    code = parse_qs(urlsplit(cb.headers["location"]).query)["code"][0]
    got = client.post("/auth/signin/redeem", json={"code": code, "device_secret": secret})
    assert got.status_code == 200, got.text
    body = got.json()
    assert decode_claims(body["token"], stack.auth).name == "dora.example"
    assert body["user"]["name"] == "dora.example"
