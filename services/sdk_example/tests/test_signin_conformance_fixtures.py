# ruff: noqa: F811
"""The shapes the REAL stack answers with, against the cross-language contract fixtures in fixtures/signin/."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bond_signin import MESSAGES, STATUS_FOR_CODE, ScopePolicy, ScopeSet, wanted_sets
from signin_conformance_support import (  # noqa: F401
    GOOGLE,
    MICROSOFT,
    NATIVE_RETURN,
    ORIGIN,
    REDIRECT,
    callback,
    client,
    device_pair,
    native_sign_in,
    redeem_pair,
    stack,
    web_sign_in,
    web_start,
)

FIXTURES = Path(__file__).resolve().parents[2].parent / "fixtures" / "signin"


def fx(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def assert_shape(actual, expected, path: str = "$") -> None:
    """Same keys and the same JSON type at every leaf (values are not compared; a list is matched to its first item)."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected an object, got {type(actual).__name__}"
        assert set(actual) == set(expected), f"{path}: keys {sorted(actual)} != fixture {sorted(expected)}"
        for key in expected:
            assert_shape(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and actual, f"{path}: expected a non-empty list"
        for i, item in enumerate(actual):
            assert_shape(item, expected[0], f"{path}[{i}]")
    else:
        assert type(actual) is type(expected), f"{path}: {type(actual).__name__} != fixture {type(expected).__name__}"


def query_keys(url: str) -> set[str]:
    return set(parse_qs(urlsplit(url).query))


def test_start_request_fixtures_are_accepted_and_answer_the_start_response_shape(client):
    web = fx("start_request_web")
    r = client.post(f"/auth/signin/{GOOGLE}/start", json={**web, "redirect_to": REDIRECT}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert_shape(r.json(), fx("start_response"))
    assert "state" in query_keys(r.json()["url"])

    native = fx("start_request_native")
    r = client.post(f"/auth/signin/{GOOGLE}/start", json={**native, "redirect_to": f"{NATIVE_RETURN}/{GOOGLE}"})
    assert r.status_code == 200, r.text
    assert_shape(r.json(), fx("start_response"))


def test_callback_redirects_match_the_fixture(stack, client):
    want = fx("callback_redirects")
    ok = web_sign_in(client)
    assert query_keys(ok.headers["location"]) == query_keys(want["web_ok"])
    refused = web_sign_in(client, GOOGLE, "stranger@example.com")
    assert query_keys(refused.headers["location"]) == query_keys(want["web_error"])
    assert parse_qs(urlsplit(refused.headers["location"]).query)["signin"] == ["error"]

    _, cb = native_sign_in(client)
    assert query_keys(cb.headers["location"]) == query_keys(want["native_return"])
    assert urlsplit(cb.headers["location"]).path == f"/app/return/{GOOGLE}"
    assert urlsplit(want["native_return"]).path == "/app/return/google"
    _, cb = native_sign_in(client, email="stranger@example.com")
    assert query_keys(cb.headers["location"]) == query_keys(want["native_error"])


def test_redeem_and_refresh_answers_match_the_fixtures(client):
    secret, challenge = device_pair()
    request = fx("redeem_request")
    assert set(request) == {"code", "device_secret", "device_label"}
    from signin_conformance_support import native_start

    state = native_start(client, challenge)
    cb = callback(client, GOOGLE, state, "demo.google@example.com")
    code = parse_qs(urlsplit(cb.headers["location"]).query)["code"][0]
    r = client.post("/auth/signin/redeem", json={**request, "code": code, "device_secret": secret})
    assert r.status_code == 200, r.text
    assert_shape(r.json(), fx("redeem_response"))

    body = fx("refresh_request_body")
    assert set(body) == {"refresh_token", "rotation_id", "delivery"}
    r2 = client.post("/auth/refresh", json={**body, "refresh_token": r.json()["refresh_token"]})
    assert r2.status_code == 200, r2.text
    assert_shape(r2.json(), fx("refresh_response"))


def test_error_envelope_matches_the_fixture(client):
    r = client.post("/auth/signin/redeem", json={"code": "nope", "device_secret": "nope"})
    assert r.status_code == 401
    assert_shape(r.json(), fx("error_envelope"))
    r = client.post("/auth/refresh", json={}, headers=ORIGIN)
    assert_shape(r.json(), fx("error_envelope"))


def test_providers_payload_matches_the_fixture(client):
    assert_shape(client.get("/auth/providers").json(), fx("providers_payload"))


def test_wanted_list_matches_the_fixture():
    policy = ScopePolicy(signin={}, by_capability={"connections.manage": (ScopeSet(
        "mail", "google", ("https://www.googleapis.com/auth/gmail.send",), "Send e-mail"),)})
    got = wanted_sets(policy, ["connections.manage"], "google", [])
    assert_shape(got, fx("wanted_list"))
    assert got == fx("wanted_list")  # same ids, scopes and flag for the same policy


def test_code_list_matches_the_lib_tables():
    codes = set(fx("labels_codes")["codes"])
    assert codes == set(STATUS_FOR_CODE), f"only in fixture {codes - set(STATUS_FOR_CODE)}; only in lib {set(STATUS_FOR_CODE) - codes}"
    assert not [c for c in codes if c not in MESSAGES], "codes without a message"
