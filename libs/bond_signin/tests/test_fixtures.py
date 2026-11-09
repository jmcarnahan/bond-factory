"""The shared fixtures in fixtures/signin/ are what this lib produces (shapes; values are generic)."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bond_signin import STATUS_FOR_CODE, wanted_sets

from .conftest import APP_ORIGIN, POLICY, native_start, start_web, state_of

FIX = Path(__file__).resolve().parents[3] / "fixtures" / "signin"


def load(name: str):
    return json.loads((FIX / name).read_text())


def query(url: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_fixture_files_are_small_and_complete():
    names = {p.name for p in FIX.glob("*.json")}
    assert names == {
        "start_request_web.json", "start_request_native.json", "start_response.json", "callback_redirects.json",
        "redeem_request.json", "redeem_response.json", "refresh_request_body.json", "refresh_response.json",
        "error_envelope.json", "providers_payload.json", "wanted_list.json", "labels_codes.json"}
    assert all((FIX / n).stat().st_size < 4096 for n in names)


def test_start_answers_match_the_fixtures(h):
    web = load("start_request_web.json")
    resp = h.client.post("/auth/signin/google/start", headers={"Origin": APP_ORIGIN}, json=web)
    assert resp.status_code == 200 and set(resp.json()) == set(load("start_response.json"))
    native = load("start_request_native.json")
    native["redirect_to"] = "http://testserver/app/return/google"  # the harness's own origin
    resp = h.client.post("/auth/signin/google/start", json=native)
    assert resp.status_code == 200 and set(resp.json()) == set(load("start_response.json"))


def test_callback_redirects_match_the_fixtures(h):
    fx = load("callback_redirects.json")
    ok = h.client.get(f"/auth/signin/google/callback?state={state_of(start_web(h))}&code=alice").headers["location"]
    assert query(ok) == query(fx["web_ok"])
    bad = h.client.get(f"/auth/signin/google/callback?state={state_of(start_web(h))}&code=stranger")
    assert query(bad.headers["location"]) == query(fx["web_error"])
    native = h.client.get(f"/auth/signin/google/callback?state={state_of(native_start(h))}&code=alice")
    assert set(query(native.headers["location"])) == set(query(fx["native_return"]))
    refused = h.client.get(f"/auth/signin/google/callback?state={state_of(native_start(h))}&code=stranger")
    assert query(refused.headers["location"]) == query(fx["native_error"])


def test_redeem_answer_matches_the_fixture(h):
    code = query(h.client.get(
        f"/auth/signin/google/callback?state={state_of(native_start(h))}&code=alice").headers["location"])["code"]
    request = load("redeem_request.json")
    resp = h.client.post("/auth/signin/redeem", json={**request, "code": code})
    expected = load("redeem_response.json")
    assert set(resp.json()) == set(expected) and set(resp.json()["user"]) == set(expected["user"])


def test_refresh_answer_matches_the_fixture(h):
    token = h.sessions._mint("u-alice", "google").refresh_token
    request = {**load("refresh_request_body.json"), "refresh_token": token}
    assert set(request) == set(load("refresh_request_body.json"))
    resp = h.client.post("/auth/refresh", json=request)
    expected = load("refresh_response.json")
    assert set(resp.json()) == set(expected) and set(resp.json()["user"]) == set(expected["user"])


def test_error_envelope_matches_the_fixture(h):
    resp = h.client.post("/auth/refresh", json={"refresh_token": "t"})  # fake store: unknown token
    assert set(resp.json()) == set(load("error_envelope.json"))
    assert set(resp.json()["detail"]) == set(load("error_envelope.json")["detail"])


def test_providers_payload_matches_the_fixture(h):
    body = h.client.get("/auth/providers").json()
    expected = load("providers_payload.json")
    assert {k: body[k] for k in expected} == expected


def test_wanted_list_matches_the_fixture():
    assert wanted_sets(POLICY, ["connections.manage"], "google", []) == load("wanted_list.json")


def test_code_list_fixture_is_the_status_table():
    assert load("labels_codes.json") == {"codes": sorted(STATUS_FOR_CODE)}
