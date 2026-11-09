"""Web sign-in: start (nonce cookie), callback (binding, order, cookies), refusals as redirects."""

import re

import pytest
from fastapi.testclient import TestClient

from .conftest import APP_ORIGIN, OWN_ORIGIN, build, start_web, state_of

DONE = f"{APP_ORIGIN}/done"


def cookies_of(resp) -> dict[str, str]:
    return {c.split("=", 1)[0]: c for c in resp.headers.get_list("set-cookie")}


def test_start_sets_per_flow_nonce_cookie_with_flags(h):
    resp = start_web(h)
    assert resp.status_code == 200 and resp.json()["url"].startswith("https://idp.example/")
    (name, raw), = cookies_of(resp).items()
    assert re.fullmatch(r"bond_signin_[0-9a-f]{8}", name)
    low = raw.lower()
    assert "httponly" in low and "samesite=lax" in low and "path=/auth/signin" in low and "max-age=600" in low
    assert "secure" not in low.replace("samesite", "")  # cookie_secure=False in this harness
    assert h.flow.started[0]["scopes"] == ["openid", "email", "profile"] and h.flow.started[0]["device_hash"] is None


def test_start_cookie_is_secure_when_configured():
    from .conftest import make_settings
    h = build(settings=make_settings(public_base="https://api.example.org", allow_http=False, cookie_secure=True))
    resp = h.client.post("/auth/signin/google/start", headers={"Origin": APP_ORIGIN},
                         json={"redirect_to": DONE, "mode": "web"})
    assert "; secure" in next(iter(cookies_of(resp).values())).lower()


def test_start_unknown_provider_is_404(h):
    assert start_web(h, provider="github").status_code == 404


@pytest.mark.parametrize("body", [
    {"redirect_to": "https://evil.example/x", "mode": "web"},
    {"redirect_to": "javascript:alert(1)", "mode": "web"},
    {"mode": "web"},
    {"redirect_to": DONE, "mode": "sideways"},
    {"redirect_to": 5, "mode": "web"},
])
def test_start_bad_body_is_400_invalid_request(h, body):
    resp = h.client.post("/auth/signin/google/start", headers={"Origin": APP_ORIGIN}, json=body)
    assert resp.status_code == 400 and resp.json()["detail"]["code"] == "invalid_request"
    assert h.flow.started == []


def test_start_not_json_is_400(h):
    resp = h.client.post("/auth/signin/google/start", headers={"Origin": APP_ORIGIN}, content=b"[1,2]")
    assert resp.status_code == 400


def test_start_flow_error_maps_by_code(h):
    h.flow.fail_start = "invalid_request"
    assert start_web(h).status_code == 400
    h.flow.fail_start = "weird_code"
    assert start_web(h).status_code == 500


def test_callback_success_sets_session_cookies_and_redirects(h):
    state = state_of(start_web(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.status_code == 302 and resp.headers["location"] == f"{DONE}?signin=ok"
    jar = cookies_of(resp)
    assert jar["app_access_token"].startswith("app_access_token=jwt-u-alice")
    refresh = jar["app_refresh_token"].lower()
    assert "httponly" in refresh and "samesite=lax" in refresh and "path=/auth" in refresh
    assert any(k.startswith("bond_signin_") and "max-age=0" in v.lower() for k, v in jar.items())  # nonce cleared
    assert h.sessions.issued[0]["user_id"] == "u-alice" and h.sessions.issued[0]["provider"] == "google"
    assert h.directory.signins == [{"user": "u-alice", "provider": "google", "ip": "203.0.113.9", "first": True}]
    assert h.directory.links == [("u-alice", "google", "sub-alice")]
    assert h.db.commits >= 1 and h.db.rollbacks == 0


def test_identity_only_signin_stores_no_connection(h):
    state = state_of(start_web(h))
    h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert h.flow.stored == [] and h.handoffs.issued == []


def test_offline_scopes_store_one_connection_under_the_signed_in_user(h):
    state = state_of(start_web(h, provider="microsoft"))
    resp = h.client.get(f"/auth/signin/microsoft/callback?state={state}&code=bob")
    assert resp.status_code == 302 and "signin=ok" in resp.headers["location"]
    assert h.flow.stored == [{"owner": "u-bob", "model": "CONN", "pending": "PENDING"}]


def test_redirect_to_keeps_its_query_and_its_fragment_after_the_query(h):
    state = state_of(start_web(h, redirect_to=f"{DONE}?lang=de#frag"))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.headers["location"] == f"{DONE}?lang=de&signin=ok#frag"


def test_hash_route_fragment_is_kept(h):
    state = state_of(start_web(h, redirect_to=f"{APP_ORIGIN}/#/auth"))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.headers["location"] == f"{APP_ORIGIN}/?signin=ok#/auth"


def test_attacker_link_without_the_nonce_cookie_is_refused_and_nothing_happens(h):
    state = state_of(start_web(h))  # the attacker's own flow
    victim = TestClient(h.app, base_url=OWN_ORIGIN, follow_redirects=False)  # a browser that never ran start
    resp = victim.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.status_code == 400 and resp.json()["detail"]["code"] == "invalid_state"
    assert "location" not in resp.headers
    assert h.directory.refusals == [] and h.flow.completed == [] and h.flow.stored == []
    assert h.sessions.issued == [] and h.directory.signins == []


def test_cookie_of_another_flow_does_not_bind_this_state(h):
    first = state_of(start_web(h))
    other = TestClient(h.app, base_url=OWN_ORIGIN, follow_redirects=False)
    start_web(h, client=other)  # the victim holds the cookie of a different flow
    resp = other.get(f"/auth/signin/google/callback?state={first}&code=alice")
    assert resp.status_code == 400 and h.sessions.issued == [] and h.directory.refusals == []


def test_forged_cookie_value_for_the_right_name_is_refused(h):
    resp = start_web(h)
    name = next(iter(cookies_of(resp)))
    victim = TestClient(h.app, base_url=OWN_ORIGIN, follow_redirects=False, cookies={name: "guess"})
    assert victim.get(f"/auth/signin/google/callback?state={state_of(resp)}&code=alice").status_code == 400


def test_two_tabs_with_two_cookies_both_succeed(h):
    s1, s2 = state_of(start_web(h)), state_of(start_web(h))
    r1 = h.client.get(f"/auth/signin/google/callback?state={s1}&code=alice")
    r2 = h.client.get(f"/auth/signin/google/callback?state={s2}&code=bob")
    assert r1.status_code == r2.status_code == 302
    assert "signin=ok" in r1.headers["location"] and "signin=ok" in r2.headers["location"]
    assert [i["user_id"] for i in h.sessions.issued] == ["u-alice", "u-bob"]


def test_missing_or_unknown_state_is_400(h):
    assert h.client.get("/auth/signin/google/callback?code=alice").status_code == 400
    assert h.client.get("/auth/signin/google/callback?state=nope&code=alice").status_code == 400


def test_refusal_redirects_with_reason_records_and_commits(h):
    state = state_of(start_web(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=stranger")
    assert resp.status_code == 302 and resp.headers["location"] == f"{DONE}?signin=error&reason=not_invited"
    assert h.directory.refusals[0]["reason"] == "not_invited"
    assert h.db.commits == 1 and h.db.rollbacks == 0  # the audit row survives
    assert h.sessions.issued == [] and h.flow.stored == [] and "app_access_token" not in cookies_of(resp)


def test_deactivated_user_is_refused_before_any_link(h):
    state = state_of(start_web(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=carol")
    assert resp.headers["location"].endswith("reason=deactivated") and h.directory.links == []


def test_unverified_email_refused(h):
    h.flow.identities["alice"] = {"email_verified": False}
    state = state_of(start_web(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.headers["location"].endswith("reason=email_not_verified")


@pytest.mark.parametrize("code", ["tenant_mismatch", "invalid_id_token", "provider_error", "signin_expired"])
def test_flow_refusals_redirect_with_their_code_and_record_nothing(h, code):
    state = state_of(start_web(h))
    h.flow.fail_complete = code
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.status_code == 302 and resp.headers["location"].endswith(f"signin=error&reason={code}")
    assert h.directory.refusals == [{"reason": code, "email": None, "user": None, "provider": "google",
                                     "ip": "203.0.113.9"}]
    assert h.sessions.issued == [] and h.db.rollbacks == 0


def test_flow_invalid_state_is_a_400_not_a_redirect(h):
    state = state_of(start_web(h))
    h.flow.fail_complete = "invalid_state"
    assert h.client.get(f"/auth/signin/google/callback?state={state}&code=alice").status_code == 400
    assert [r["reason"] for r in h.directory.refusals] == ["invalid_state"]


def test_a_provider_error_string_from_the_flow_is_shown_as_provider_error(h):
    state = state_of(start_web(h))
    h.flow.fail_complete = "invalid_grant"
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.status_code == 302 and resp.headers["location"].endswith("reason=provider_error")
    assert [r["reason"] for r in h.directory.refusals] == ["provider_error"] and h.sessions.issued == []


def test_a_flow_error_without_a_code_is_not_swallowed(h):
    state = state_of(start_web(h))

    def boom(**kw):
        raise RuntimeError("bug")

    h.flow.complete = boom
    with pytest.raises(RuntimeError):
        h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")


def test_access_denied_is_consent_declined_without_calling_complete(h):
    state = state_of(start_web(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&error=access_denied")
    assert resp.headers["location"] == f"{DONE}?signin=error&reason=consent_declined"
    assert h.flow.completed == []
    assert [(r["reason"], r["email"], r["user"]) for r in h.directory.refusals] == [("consent_declined", None, None)]


def test_other_provider_error_is_provider_error(h):
    state = state_of(start_web(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&error=server_error")
    assert resp.headers["location"].endswith("reason=provider_error")
    assert [r["reason"] for r in h.directory.refusals] == ["provider_error"]


def test_missing_code_without_error_redirects_invalid_request(h):
    state = state_of(start_web(h))
    resp = h.client.get(f"/auth/signin/google/callback?state={state}")
    assert resp.headers["location"].endswith("reason=invalid_request")


def test_callback_unknown_provider_is_404(h):
    assert h.client.get("/auth/signin/github/callback?state=x&code=y").status_code == 404


def test_expired_state_redirects_with_signin_expired_and_records(h):
    state = state_of(start_web(h))
    h.flow.states[state].expired = True
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.status_code == 302 and resp.headers["location"] == f"{DONE}?signin=error&reason=signin_expired"
    assert h.flow.completed == [] and h.sessions.issued == []
    assert [r["reason"] for r in h.directory.refusals] == ["signin_expired"]


def test_expired_state_without_the_nonce_cookie_is_still_a_400(h):
    state = state_of(start_web(h))
    h.flow.states[state].expired = True
    victim = TestClient(h.app, base_url=OWN_ORIGIN, follow_redirects=False)
    assert victim.get(f"/auth/signin/google/callback?state={state}&code=alice").status_code == 400
    assert h.directory.refusals == []


def test_state_for_another_provider_is_400_before_any_work(h):
    state = state_of(start_web(h, provider="google"))
    resp = h.client.get(f"/auth/signin/microsoft/callback?state={state}&code=alice")
    assert resp.status_code == 400 and resp.json()["detail"]["code"] == "invalid_state"
    assert h.flow.completed == [] and h.directory.refusals == [] and h.sessions.issued == []


def test_invalid_state_clears_the_flow_cookie_when_its_name_is_known(h):
    state = state_of(start_web(h))
    victim = TestClient(h.app, base_url=OWN_ORIGIN, follow_redirects=False,
                        cookies={"bond_signin_00000000": "x"})
    resp = victim.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.status_code == 400
    assert any(k.startswith("bond_signin_") and "max-age=0" in v.lower() for k, v in cookies_of(resp).items())


def test_non_ascii_cookie_value_is_a_400_not_a_500(h):
    resp = start_web(h)
    name = next(iter(cookies_of(resp)))
    victim = TestClient(h.app, base_url=OWN_ORIGIN, follow_redirects=False)
    got = victim.get(f"/auth/signin/google/callback?state={state_of(resp)}&code=alice",
                     headers={"Cookie": f"{name}=caf\u00e9".encode("latin-1")})
    assert got.status_code == 400 and h.sessions.issued == []


def test_web_redirect_to_is_rechecked_against_the_allowlist_at_callback(h):
    state = state_of(start_web(h))
    h.flow.states[state].redirect_to = "https://evil.example/steal"  # as if the allowlist changed since start
    resp = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    assert resp.status_code == 400 and "location" not in resp.headers
    assert h.flow.completed == [] and h.sessions.issued == []
