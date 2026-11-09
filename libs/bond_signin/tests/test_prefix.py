"""The router mounted under another prefix: routes, cookie paths and the return page move together."""


from bond_signin import IdentityTaken, SignInRefused, refusal_code

from .conftest import APP_ORIGIN, OWN_ORIGIN, build, make_settings, sha, state_of

PREFIX = "/api/v1/auth"


def cookies_of(resp) -> dict[str, str]:
    return {c.split("=", 1)[0]: c for c in resp.headers.get_list("set-cookie")}


def test_web_flow_end_to_end_under_a_prefix():
    h = build(prefix=PREFIX)
    start = h.client.post(f"{PREFIX}/signin/google/start", headers={"Origin": APP_ORIGIN},
                          json={"redirect_to": f"{APP_ORIGIN}/done", "mode": "web"})
    assert start.status_code == 200
    (nonce_cookie,) = cookies_of(start).values()
    assert f"path={PREFIX}/signin".lower() in nonce_cookie.lower()
    done = h.client.get(f"{PREFIX}/signin/google/callback?state={state_of(start)}&code=alice")
    assert done.status_code == 302 and done.headers["location"].endswith("signin=ok")
    jar = cookies_of(done)
    assert f"path={PREFIX}".lower() in jar["app_refresh_token"].lower()
    assert "path=/;" in jar["app_access_token"].lower() or "path=/" in jar["app_access_token"].lower()
    assert any("max-age=0" in v.lower() and f"path={PREFIX}/signin".lower() in v.lower()
               for k, v in jar.items() if k.startswith("bond_signin_"))


def test_default_routes_are_absent_under_a_prefix_and_present_by_default():
    h = build(prefix=PREFIX)
    assert h.client.post("/auth/refresh", json={"refresh_token": "t"}).status_code == 404
    assert h.client.post(f"{PREFIX}/refresh", json={"refresh_token": "t"}).status_code != 404
    assert build().client.post("/auth/refresh", json={"refresh_token": "t"}).status_code != 404


def test_refresh_and_logout_cookie_paths_follow_the_prefix():
    h = build(prefix=PREFIX)
    token = h.sessions._mint("u-alice", "google").refresh_token
    resp = h.client.post(f"{PREFIX}/refresh", headers={"Origin": APP_ORIGIN, "Cookie": f"app_refresh_token={token}"},
                         json={})
    assert resp.status_code == 200
    assert f"path={PREFIX}".lower() in cookies_of(resp)["app_refresh_token"].lower()
    out = h.client.post(f"{PREFIX}/logout", headers={"Origin": APP_ORIGIN})
    cleared = cookies_of(out)["app_refresh_token"].lower()
    assert "max-age=0" in cleared and f"path={PREFIX}".lower() in cleared


def test_native_start_redeem_providers_and_return_page_under_a_prefix():
    h = build(settings=make_settings(prefix=PREFIX))
    body = {"mode": "native", "device_challenge": sha("s" * 32), "attempt": "att_1",
            "redirect_to": h.settings.native_return_base + "/google"}
    started = h.client.post(f"{PREFIX}/signin/google/start", json=body)
    assert started.status_code == 200
    cb = h.client.get(f"{PREFIX}/signin/google/callback?state={state_of(started)}&code=alice")
    code = cb.headers["location"].split("code=")[1]
    redeemed = h.client.post(f"{PREFIX}/signin/redeem", json={"code": code, "device_secret": "s" * 32})
    assert redeemed.status_code == 200 and redeemed.json()["refresh_token"]
    assert h.client.get(f"{PREFIX}/providers").status_code == 200
    assert h.settings.native_return_base == f"{OWN_ORIGIN}/api/v1/app/return"
    assert h.settings.return_path_prefix == "/api/v1/app/return/"
    page = h.client.get(h.settings.native_return_base.removeprefix(OWN_ORIGIN) + "/google")
    assert page.status_code == 200 and "Return to the app" in page.text


def test_an_explicit_refresh_path_wins_over_the_prefix():
    from dataclasses import replace

    from fastapi import Response

    from bond_signin import clear_session_cookies, finish_session

    from .conftest import COOKIES, make_settings

    policy = replace(COOKIES, refresh_path="/custom")
    reply = Response()
    finish_session(reply, __import__("bond_signin").IssuedSession("j", "r", "f", 1), settings=make_settings(),
                   cookies=policy, delivery="cookie")
    assert "path=/custom" in reply.headers.getlist("set-cookie")[1].lower()
    clear = Response()
    clear_session_cookies(clear, settings=make_settings(), cookies=policy)
    assert any("path=/custom" in c.lower() for c in clear.headers.getlist("set-cookie"))


def test_identity_taken_is_a_signin_refusal_with_the_mismatch_code():
    assert isinstance(IdentityTaken(), SignInRefused) and refusal_code(IdentityTaken()) == "identity_mismatch"


def test_settings_prefix_drives_callback_url_and_the_router_default():
    from .conftest import make_settings

    s = make_settings(prefix="/api/v1/auth/")
    assert s.prefix == "/api/v1/auth"
    assert s.callback_url("google") == "http://testserver/api/v1/auth/signin/google/callback"
    h = build(settings=s)  # no prefix argument: the settings value is used
    assert h.client.post("/auth/refresh", json={"refresh_token": "t"}).status_code == 404
    assert h.client.post(f"{PREFIX}/refresh", json={"refresh_token": "t"}).status_code != 404


def test_prefix_from_env():
    from bond_signin import from_env

    env = {"BOND_SIGNIN_PUBLIC_BASE": "https://api.example.org", "BOND_SIGNIN_PREFIX": "/api/v1/auth"}
    assert from_env(env=env).prefix == "/api/v1/auth"
    assert from_env(env={"BOND_SIGNIN_PUBLIC_BASE": "https://api.example.org"}).prefix == "/auth"


def test_default_prefix_keeps_the_original_return_urls():
    from .conftest import make_settings

    s = make_settings()
    assert s.native_return_base == f"{OWN_ORIGIN}/app/return" and s.return_path_prefix == "/app/return/"
    custom = make_settings(prefix="/auth", native_return_base="https://x.example.org/r")
    assert custom.native_return_base == "https://x.example.org/r"
