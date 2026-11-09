"""Settings, finish_session, the return page, the package barrel."""

import re

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

import bond_signin
from bond_signin import IssuedSession, SignInSettings, finish_session, from_env

from .conftest import COOKIES, make_settings

ISSUED = IssuedSession(access_jwt="jwt", refresh_token="rt", family_id="f", expires_in=3600)


def test_settings_requires_https_public_base_unless_allowed():
    with pytest.raises(ValueError):
        SignInSettings(providers=("google",), public_base="http://api.example.org")
    ok = SignInSettings(providers=("google",), public_base="https://api.example.org/", cookie_secure=True)
    assert ok.public_base == "https://api.example.org"


@pytest.mark.parametrize("base", ["", "api.example.org", "ftp://x.org"])
def test_settings_rejects_non_urls(base):
    with pytest.raises(ValueError):
        SignInSettings(providers=(), public_base=base, allow_http=True)


def test_settings_derives_native_return_base_and_own_origin():
    s = SignInSettings(providers=("google",), public_base="https://api.example.org")
    assert s.native_return_base == "https://api.example.org/app/return"
    assert s.own_origin == "https://api.example.org"
    assert s.callback_url("google") == "https://api.example.org/auth/signin/google/callback"
    custom = SignInSettings(providers=(), public_base="https://api.example.org", native_return_base="https://x.org/r/")
    assert custom.native_return_base == "https://x.org/r"


def test_settings_allowed_origins_include_own_and_allowlist():
    s = make_settings(redirect_allowlist=("https://App.Example.org/path",))
    assert s.allowed_origins == {"https://app.example.org", "http://testserver"}


def test_native_scheme_ok():
    s = make_settings(native_schemes=("com.example.app",))
    assert s.native_scheme_ok("com.example.app://return/google")
    assert not s.native_scheme_ok("com.evil.app://return") and not s.native_scheme_ok("https://x.org")
    assert not make_settings(native_schemes=()).native_scheme_ok("com.example.app://x")


def test_from_env_reads_the_prefixed_variables():
    env = {"BOND_SIGNIN_PROVIDERS": "google, microsoft", "BOND_SIGNIN_PUBLIC_BASE": "https://api.example.org",
           "BOND_SIGNIN_REDIRECT_ALLOWLIST": "https://a.example.org,https://b.example.org",
           "BOND_SIGNIN_NATIVE_SCHEMES": "com.example.app", "BOND_SIGNIN_BREAKGLASS": "1"}
    s = from_env(env=env)
    assert s.providers == ("google", "microsoft") and s.break_glass is True and s.cookie_secure is True
    assert s.redirect_allowlist == ("https://a.example.org", "https://b.example.org")
    assert s.native_schemes == ("com.example.app",)


def test_from_env_defaults_and_allow_http():
    s = from_env("X_", env={"X_PUBLIC_BASE": "http://localhost:8000", "X_ALLOW_HTTP": "true"})
    assert s.break_glass is False and s.cookie_secure is False and s.providers == ()
    with pytest.raises(ValueError):
        from_env("X_", env={})


def test_finish_session_cookie_delivery():
    reply = Response()
    body = finish_session(reply, ISSUED, settings=make_settings(), cookies=COOKIES, delivery="cookie")
    assert body == {"token": "jwt", "expires_in": 3600}
    names = [c.split("=")[0] for c in reply.headers.getlist("set-cookie")]
    assert names == ["app_access_token", "app_refresh_token"]


def test_finish_session_body_delivery_sets_no_cookie():
    reply = Response()
    body = finish_session(reply, ISSUED, settings=make_settings(), cookies=COOKIES, delivery="body")
    assert body["refresh_token"] == "rt" and reply.headers.getlist("set-cookie") == []


def test_finish_session_defaults_to_the_settings_delivery():
    reply = Response()
    body = finish_session(reply, ISSUED, settings=make_settings(), cookies=COOKIES)
    assert "refresh_token" not in body and len(reply.headers.getlist("set-cookie")) == 2


def test_return_page_is_static_with_no_external_resources(h):
    resp = h.client.get("/app/return/google?attempt=a&code=secret")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/html")
    assert "Return to the app" in resp.text
    assert not re.search(r"(src|href)\s*=|@import|url\(|https?://", resp.text, re.IGNORECASE)
    assert "secret" not in resp.text
    assert resp.headers["referrer-policy"] == "no-referrer" and "no-store" in resp.headers["cache-control"]
    assert "default-src 'none'" in resp.headers["content-security-policy"]


def test_providers_route_is_absent_unless_included():
    from bond_signin import make_signin_router

    from .conftest import POLICY, build

    h = build()
    app = FastAPI()
    app.include_router(make_signin_router(
        directory=h.directory, flow=h.flow, handoffs=h.handoffs, sessions=h.sessions, policy=POLICY,
        settings=h.settings, cookies=COOKIES, session_dep=lambda r: None, client_ip=lambda r: None,
        session_scope=h.db.scope))
    assert TestClient(app).get("/auth/providers").status_code == 404


def test_package_imports_no_sibling_lib():
    import pathlib

    root = pathlib.Path(bond_signin.__file__).parent
    for path in root.glob("*.py"):
        assert not re.search(r"^\s*(from|import)\s+bond_(oauth|auth_py|service_kit|jobs)", path.read_text(), re.MULTILINE)


def test_fakes_satisfy_the_protocols():
    from bond_signin import HandoffStore, IdentityFlow, SessionIssuer, UserDirectory

    from .fakes import FakeDirectory, FakeFlow, FakeHandoffs, FakeSessions

    assert isinstance(FakeDirectory(), UserDirectory) and isinstance(FakeFlow(), IdentityFlow)
    assert isinstance(FakeHandoffs(), HandoffStore) and isinstance(FakeSessions(), SessionIssuer)


def test_the_directory_spec_is_passed_to_issue_unchanged(h):
    from .conftest import start_web, state_of

    state = state_of(start_web(h))
    h.client.get(f"/auth/signin/google/callback?state={state}&code=alice")
    spec = h.sessions.issued[0]["spec"]
    assert (spec.sub, spec.name, spec.capabilities) == ("u-alice", "Alice", ["connections.manage"])


def test_injected_clock_moves_hand_off_expiry_and_reaches_every_call():
    from .conftest import build, native_start, state_of

    now = [1_000.0]
    h = build(clock=lambda: now[0])
    state = state_of(native_start(h))
    code = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice").headers["location"].split("code=")[1]
    now[0] += 121  # past the 120 s hand-off lifetime
    late = h.client.post("/auth/signin/redeem", json={"code": code, "device_secret": "s" * 32})
    assert late.status_code == 401
    state = state_of(native_start(h, attempt="att_2"))
    code = h.client.get(f"/auth/signin/google/callback?state={state}&code=alice").headers["location"].split("code=")[1]
    now[0] += 60
    assert h.client.post("/auth/signin/redeem", json={"code": code, "device_secret": "s" * 32}).status_code == 200


@pytest.mark.parametrize("scheme", ["http", "https", "javascript", "data", "file", "about", "vbscript", "myapp",
                                    "Bad Scheme.x", "1org.example", ""])
def test_native_schemes_must_be_reverse_domain_and_not_web(scheme):
    with pytest.raises(ValueError):
        SignInSettings(providers=(), public_base="https://api.example.org", native_schemes=(scheme,))


def test_native_scheme_reverse_domain_is_accepted():
    s = SignInSettings(providers=(), public_base="https://api.example.org", native_schemes=("org.example.app",))
    assert s.native_scheme_ok("org.example.app://return")


def test_issued_session_repr_hides_the_secrets():
    text = repr(IssuedSession(access_jwt="jwt-SECRET", refresh_token="rt-SECRET", family_id="f", expires_in=1))
    assert "SECRET" not in text and "family_id" in text


def test_messages_and_statuses_match_the_auth_lib_table_read_as_text():
    import ast
    import pathlib

    from bond_signin import MESSAGES, STATUS_FOR_CODE

    path = pathlib.Path(__file__).resolve().parents[2] / "bond_auth_py/bond_auth_py/errors.py"
    tree = ast.parse(path.read_text())
    consts = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
              and isinstance(n.value, ast.Constant) for t in n.targets}
    table = next(n.value for n in tree.body if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "REFUSALS")
    theirs = {consts[k.id]: (v.elts[0].value, v.elts[1].value) for k, v in zip(table.keys, table.values, strict=True)}
    shared = [c for c in theirs if c in MESSAGES]
    assert len(shared) >= 15
    for code in shared:
        assert MESSAGES[code] == theirs[code][1], code
        assert STATUS_FOR_CODE[code] == theirs[code][0], code


def test_barrel_exports_the_protocol_types():
    import bond_signin

    for name in ("StateInfo", "OidcIdentity", "StartedSignIn", "SignInResult"):
        assert hasattr(bond_signin, name) and name in bond_signin.__all__


def test_insecure_cookies_on_an_https_base_are_refused_unless_allow_http():
    with pytest.raises(ValueError):
        SignInSettings(providers=(), public_base="https://api.example.org", cookie_secure=False)
    ok = SignInSettings(providers=(), public_base="https://api.example.org", cookie_secure=False, allow_http=True)
    assert ok.cookie_secure is False
