"""Refresh rotation, logout, revoke-all, the Origin matrix, rate-limit keys, providers."""

import pytest

from .conftest import APP_ORIGIN, OWN_ORIGIN

REFRESH_COOKIE = "app_refresh_token"


def call(h, url, *, cookies=None, headers=None, **kw):
    """POST with a Cookie header (per-request ``cookies=`` is deprecated in httpx)."""
    merged = dict(headers or {})
    if cookies:
        merged["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return h.client.post(url, headers=merged, **kw)


def sign_in_cookie(h) -> str:
    """Issue a session for alice and return its refresh token."""
    return h.sessions._mint("u-alice", "google").refresh_token


def set_cookies(resp) -> dict[str, str]:
    return {c.split("=", 1)[0]: c for c in resp.headers.get_list("set-cookie")}


def test_refresh_with_cookie_rotates_sets_flags_and_hides_token_from_body(h):
    token = sign_in_cookie(h)
    resp = call(h, "/auth/refresh", headers={"Origin": APP_ORIGIN}, json={},
                         cookies={REFRESH_COOKIE: token})
    body = resp.json()
    assert resp.status_code == 200 and body["token"].startswith("jwt-u-alice") and "refresh_token" not in body
    assert body["user"]["id"] == "u-alice"
    jar = set_cookies(resp)
    refresh = jar[REFRESH_COOKIE].lower()
    assert "httponly" in refresh and "samesite=lax" in refresh and "path=/auth" in refresh
    assert not jar[REFRESH_COOKIE].startswith(f"{REFRESH_COOKIE}={token};")
    assert "app_access_token" in jar


def test_refresh_with_body_token_returns_it_in_json_and_sets_no_cookie(h):
    token = sign_in_cookie(h)
    resp = h.client.post("/auth/refresh", json={"refresh_token": token})  # no Origin: native
    body = resp.json()
    assert resp.status_code == 200 and body["refresh_token"] != token and body["refresh_token"].startswith("rt-")
    assert "set-cookie" not in resp.headers


def test_cookie_sourced_refresh_with_origin_answers_in_cookies(h):
    token = sign_in_cookie(h)
    resp = call(h, "/auth/refresh", headers={"Origin": APP_ORIGIN}, json={"delivery": "cookie"},
                cookies={REFRESH_COOKIE: token})
    assert resp.status_code == 200 and "refresh_token" not in resp.json()


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example"}, {"Origin": "null"}])
def test_cookie_token_cannot_dodge_the_origin_rule_by_asking_for_body_delivery(h, headers):
    token = sign_in_cookie(h)
    resp = call(h, "/auth/refresh", headers=headers, json={"delivery": "body"}, cookies={REFRESH_COOKIE: token})
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "invalid_origin"
    assert h.sessions.rotations == []


def test_cookie_token_with_origin_ignores_a_body_delivery_request(h):
    token = sign_in_cookie(h)
    resp = call(h, "/auth/refresh", headers={"Origin": APP_ORIGIN}, json={"delivery": "body"},
                cookies={REFRESH_COOKIE: token})
    assert resp.status_code == 200 and "refresh_token" not in resp.json()
    assert REFRESH_COOKIE in set_cookies(resp)


def test_body_token_without_origin_is_allowed_for_native(h):
    resp = h.client.post("/auth/refresh", json={"refresh_token": sign_in_cookie(h), "delivery": "body"})
    assert resp.status_code == 200 and resp.json()["refresh_token"]


def test_rotation_id_is_passed_through_and_junk_is_dropped(h):
    t1, t2 = sign_in_cookie(h), sign_in_cookie(h)
    h.client.post("/auth/refresh", json={"refresh_token": t1, "rotation_id": "rid-1"})
    h.client.post("/auth/refresh", json={"refresh_token": t2, "rotation_id": 12345})
    assert [r["rotation_id"] for r in h.sessions.rotations] == ["rid-1", None]


def test_provider_probe_is_wired_to_the_directory(h):
    h.directory.by_id["u-alice"].alive = True
    h.client.post("/auth/refresh", json={"refresh_token": sign_in_cookie(h)})
    assert h.sessions.probe_results == [True]


@pytest.mark.parametrize("code", ["refresh_reused", "refresh_expired", "refresh_revoked"])
def test_refresh_errors_are_401_and_clear_the_cookies(h, code):
    h.sessions.rotate_error = code
    resp = call(h, "/auth/refresh", headers={"Origin": APP_ORIGIN}, json={}, cookies={REFRESH_COOKIE: "t"})
    assert resp.status_code == 401 and resp.json()["detail"]["code"] == code
    jar = set_cookies(resp)
    assert "max-age=0" in jar[REFRESH_COOKIE].lower() and "app_access_token" in jar


def test_refresh_reuse_is_committed_not_rolled_back(h):
    h.sessions.rotate_error = "refresh_reused"
    h.client.post("/auth/refresh", json={"refresh_token": "t"})
    assert h.db.commits == 1 and h.db.rollbacks == 0


def test_refresh_body_error_does_not_set_cookies(h):
    h.sessions.rotate_error = "refresh_expired"
    resp = h.client.post("/auth/refresh", json={"refresh_token": "t"})
    assert resp.status_code == 401 and "set-cookie" not in resp.headers


def test_refresh_without_any_token_is_401_invalid_token(h):
    resp = h.client.post("/auth/refresh", headers={"Origin": APP_ORIGIN}, json={})
    assert resp.status_code == 401 and resp.json()["detail"]["code"] == "invalid_token"


def test_refresh_of_a_deactivated_user_is_refused(h):
    token = sign_in_cookie(h)
    h.directory.by_id["u-alice"].is_active = False
    resp = h.client.post("/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401 and resp.json()["detail"]["code"] == "refresh_revoked"


def test_legacy_id_token_body_is_delegated_with_an_allowed_origin(h):
    resp = h.client.post("/auth/refresh", headers={"Origin": APP_ORIGIN}, json={"id_token": "abc"})
    assert resp.json() == {"legacy": True} and h.legacy_calls == [{"id_token": "abc"}]
    assert h.sessions.rotations == []


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example"}, {"Origin": "null"}])
def test_legacy_id_token_needs_an_origin_unless_bearer(h, headers):
    resp = h.client.post("/auth/refresh", headers=headers, json={"id_token": "x"})
    assert resp.status_code == 403 and resp.json()["detail"]["code"] == "invalid_origin"
    assert h.legacy_calls == []


def test_legacy_id_token_with_a_bearer_header_skips_the_origin_rule(h):
    resp = h.client.post("/auth/refresh", headers={"Authorization": "Bearer abc"}, json={"id_token": "x"})
    assert resp.json() == {"legacy": True} and h.legacy_calls == [{"id_token": "x"}]


def test_refresh_token_wins_over_legacy_when_both_present(h):
    resp = h.client.post("/auth/refresh", json={"id_token": "abc", "refresh_token": sign_in_cookie(h)})
    assert h.legacy_calls == [] and resp.status_code == 200


def test_unknown_error_code_from_rotate_is_500(h):
    h.sessions.rotate_error = "mystery"
    assert h.client.post("/auth/refresh", json={"refresh_token": "t"}).status_code == 500


# ---- Origin matrix: cookie-delivery POSTs need an allowed Origin -------------------------------------------------

ORIGIN_CASES = [
    ({}, 403), ({"Origin": "null"}, 403), ({"Origin": "https://evil.example"}, 403),
    ({"Origin": OWN_ORIGIN}, "ok"), ({"Origin": APP_ORIGIN}, "ok"),
    ({"Referer": f"{APP_ORIGIN}/page?x=1"}, "ok"), ({"Referer": "https://evil.example/p"}, 403),
]


def post_for(h, route, headers):
    if route == "start":
        return h.client.post("/auth/signin/google/start", headers=headers,
                             json={"redirect_to": f"{APP_ORIGIN}/done", "mode": "web"})
    if route == "refresh":
        return call(h, "/auth/refresh", headers=headers, json={}, cookies={REFRESH_COOKIE: sign_in_cookie(h)})
    if route == "logout":
        return call(h, "/auth/logout", headers=headers, cookies={REFRESH_COOKIE: "t"})
    h.current = h.directory.by_id["u-alice"]
    return call(h, "/auth/sessions/revoke-all", headers=headers, cookies={"app_access_token": "jwt"})


@pytest.mark.parametrize("route", ["start", "refresh", "logout", "revoke-all"])
@pytest.mark.parametrize(("headers", "expected"), ORIGIN_CASES)
def test_origin_matrix(h, route, headers, expected):
    resp = post_for(h, route, headers)
    if expected == 403:
        assert resp.status_code == 403 and resp.json()["detail"]["code"] == "invalid_origin"
    else:
        assert resp.status_code == 200


def test_body_and_bearer_delivery_skip_the_origin_rule(h):
    assert h.client.post("/auth/refresh", json={"refresh_token": sign_in_cookie(h)}).status_code == 200
    assert h.client.post("/auth/logout", json={"refresh_token": "t"}).status_code == 200
    h.current = h.directory.by_id["u-alice"]
    assert h.client.post("/auth/sessions/revoke-all", headers={"Authorization": "Bearer abc"}).status_code == 200


def test_foreign_origin_does_no_work(h):
    post_for(h, "refresh", {"Origin": "https://evil.example"})
    assert h.sessions.rotations == []
    post_for(h, "logout", {"Origin": "https://evil.example"})
    assert h.sessions.revoked_tokens == []


# ---- logout and revoke-all -------------------------------------------------------------------------------------

def test_logout_revokes_the_cookie_token_and_clears_cookies(h):
    resp = call(h, "/auth/logout", headers={"Origin": APP_ORIGIN}, cookies={REFRESH_COOKIE: "tok"})
    assert resp.status_code == 200 and resp.json() == {"status": "logged_out"}
    assert h.sessions.revoked_tokens == ["tok"]
    jar = set_cookies(resp)
    assert "max-age=0" in jar[REFRESH_COOKIE].lower() and "max-age=0" in jar["app_access_token"].lower()


def test_logout_with_body_token_and_with_nothing(h):
    assert h.client.post("/auth/logout", json={"refresh_token": "tok2"}).json() == {"status": "logged_out"}
    assert h.sessions.revoked_tokens == ["tok2"]
    resp = h.client.post("/auth/logout", headers={"Origin": APP_ORIGIN})
    assert resp.status_code == 200 and h.sessions.revoked_tokens == ["tok2"]


def test_logout_never_fails_when_revocation_breaks(h):
    h.sessions.revoke_error = RuntimeError("db down")
    resp = h.client.post("/auth/logout", json={"refresh_token": "tok"})
    assert resp.status_code == 200 and resp.json() == {"status": "logged_out"}
    assert "app_refresh_token" in set_cookies(resp)


def test_logout_tolerates_a_garbage_body(h):
    assert h.client.post("/auth/logout", headers={"Origin": APP_ORIGIN}, content=b"not json").status_code == 200


def test_revoke_all_revokes_marks_and_clears(h):
    h.current = h.directory.by_id["u-alice"]
    resp = h.client.post("/auth/sessions/revoke-all", headers={"Origin": APP_ORIGIN})
    assert resp.status_code == 200 and resp.json() == {"revoked": 3}
    assert h.sessions.revoked_users == [{"user_id": "u-alice", "reason": "signout_all"}]
    assert h.directory.invalidated[0][0] == "u-alice" and h.directory.by_id["u-alice"].sessions_valid_after
    assert h.directory.invalidated[0][1].tzinfo is not None  # the lib hands an aware UTC instant
    assert "max-age=0" in set_cookies(resp)[REFRESH_COOKIE].lower()


def test_revoke_all_signed_out_is_401(h):
    resp = h.client.post("/auth/sessions/revoke-all", headers={"Origin": APP_ORIGIN})
    assert resp.status_code == 401 and h.sessions.revoked_users == []


# ---- rate limit keys, providers ---------------------------------------------------------------------------------

def test_rate_limit_is_called_with_the_route_keys(h):
    from .conftest import native_start, start_web, state_of
    state = state_of(start_web(h))
    h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    h.client.post("/auth/signin/redeem", json={"code": "x", "device_secret": "y"})
    h.client.post("/auth/refresh", json={"refresh_token": "t"})
    native_start(h)
    assert h.limits == ["signin_start", "signin_callback", "redeem", "refresh", "signin_start"]


def test_rate_limit_runs_before_work():
    import fastapi
    from fastapi.testclient import TestClient

    from bond_signin import make_signin_router

    from .conftest import COOKIES, POLICY, build

    h = build()

    def deny(request, key):
        raise fastapi.HTTPException(429, {"code": "rate_limited", "message": key})

    app = fastapi.FastAPI()
    app.include_router(make_signin_router(
        directory=h.directory, flow=h.flow, handoffs=h.handoffs, sessions=h.sessions, policy=POLICY,
        settings=h.settings, cookies=COOKIES, session_dep=lambda r: None, client_ip=lambda r: None,
        session_scope=h.db.scope, rate_limit=deny))
    resp = TestClient(app).post("/auth/refresh", json={"refresh_token": "t"})
    assert resp.status_code == 429 and h.sessions.rotations == []


def test_providers_payload_keys(h):
    body = h.client.get("/auth/providers").json()
    assert body["firebase"] is False
    assert body["signin"] == [{"id": "google", "label": "Google"}, {"id": "microsoft", "label": "Microsoft"}]
    assert body["break_glass"] is False and body["default_flow"] == "signin"
