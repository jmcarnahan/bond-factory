"""Direct sign-in through the REAL example app (not the conformance stack): web flow, refusals, the role ask,
break-glass, well-known files, the startup refusal. Fake mode, a temp SQLite file, no network."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from signin_util import (
    ACCESS,
    CONNECTIONS_PAGE,
    GOOGLE,
    MICROSOFT,
    ORIGIN,
    REFRESH,
    browser,
    connect,
    consent,
    query_of,
    rows,
    sign_in,
    start_web,
    state_in,
)
from sqlalchemy import func, select

from sdk_example.db import session_scope
from sdk_example.main import create_app
from sdk_example.models.auth import DEMO_USERS, User
from sdk_example.models.connections import OAuthConnection
from sdk_example.models.sessions import AuthSession

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "signin"


def user_row(app, email):
    return rows(app, User, email=email)[0]


def wanted(client):
    return client.get("/connections").json()["wanted"]


def test_demo_signs_in_with_cookies_and_is_bound_to_the_provider_account(app):
    client = browser(app)
    cb = sign_in(client)
    assert cb.status_code == 302 and cb.headers["location"] == "http://localhost:8078/auth?signin=ok"
    cookies = {c.split("=", 1)[0]: c.lower() for c in cb.headers.get_list("set-cookie")}
    assert "httponly" in cookies[ACCESS] and "samesite=lax" in cookies[ACCESS] and "max-age=3600" in cookies[ACCESS]
    assert "httponly" in cookies[REFRESH] and "path=/auth" in cookies[REFRESH] and "secure" not in cookies[REFRESH]
    assert "token=" not in cb.headers["location"]  # nothing secret rides in a URL
    me = client.get("/auth/me")  # the cookie alone, no bearer
    assert me.status_code == 200 and me.json()["user"]["email"] == "demo@example.com"
    user = user_row(app, "demo@example.com")
    assert user.identity_provider == GOOGLE and user.identity_subject.startswith("fake-")
    assert user.accepted_at is not None and user.last_sign_in_at is not None
    assert rows(app, OAuthConnection) == []  # identity-only sign-in stores no connection


def test_refresh_rotates_the_cookie_and_logout_ends_the_session(app):
    client = browser(app)
    sign_in(client)
    first = client.cookies.get(REFRESH)
    done = client.post("/auth/refresh", json={}, headers=ORIGIN)
    assert done.status_code == 200 and done.json()["user"]["email"] == "demo@example.com"
    assert "refresh_token" not in done.json() and client.cookies.get(REFRESH) != first
    out = client.post("/auth/logout", json={}, headers=ORIGIN)
    assert out.json() == {"status": "logged_out"} and client.cookies.get(REFRESH) is None
    assert client.get("/auth/me").status_code == 401


def test_simulate_reuse_signs_the_person_out_and_the_family_is_revoked(app):
    client = browser(app)
    sign_in(client)
    answer = client.post("/auth/simulate-reuse", headers=ORIGIN)
    assert answer.status_code == 401 and answer.json()["detail"]["code"] == "refresh_reused"
    cleared = answer.headers.get_list("set-cookie")
    assert any(c.startswith(ACCESS) and "max-age=0" in c.lower() for c in cleared)
    assert any(c.startswith(REFRESH) and "max-age=0" in c.lower() for c in cleared)
    assert all(r.revoked_at is not None for r in rows(app, AuthSession))
    assert client.post("/auth/refresh", json={}, headers=ORIGIN).status_code == 401
    assert sign_in(client).headers["location"].endswith("signin=ok")  # signing in again works


def test_an_attacker_link_callback_is_refused(app):
    attacker, victim = browser(app), browser(app)
    state = start_web(attacker)  # the attacker's state and nonce cookie
    pick = attacker.get("/connections/fake/consent/submit", params={"state": state, "identity": "demo@example.com"})
    reply = victim.get(pick.headers["location"])  # the victim's browser has no nonce cookie for this flow
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_state"
    assert not any(c.startswith(ACCESS) for c in reply.headers.get_list("set-cookie"))
    assert rows(app, AuthSession) == [] and victim.get("/auth/me").status_code == 401


def test_start_needs_an_allowed_origin(app):
    client = browser(app)
    for origin in (None, {"Origin": "null"}, {"Origin": "http://evil.example"}):
        reply = client.post(f"/auth/signin/{GOOGLE}/start", json={"redirect_to": "http://localhost:8078/auth"},
                            headers=origin or {})
        assert reply.status_code == 403 and reply.json()["detail"]["code"] == "invalid_origin", origin


def test_an_uninvited_identity_is_refused_and_no_row_appears(app):
    client = browser(app)
    before = len(rows(app, User))
    cb = sign_in(client, "uninvited@example.com")
    assert query_of(cb) == {"signin": "error", "reason": "not_invited"}
    assert len(rows(app, User)) == before and rows(app, AuthSession) == []
    assert client.get("/auth/me").status_code == 401


def test_crew_has_nothing_wanted_and_demo_has_two_sets(app):
    crew, demo = browser(app), browser(app)
    sign_in(crew, "crew@example.com")
    assert wanted(crew) == []
    sign_in(demo)
    sets = wanted(demo)
    assert [s["id"] for s in sets] == ["mail_send", "calendar"]
    assert all(s["provider"] == GOOGLE and s["granted"] is False and s["scopes"] for s in sets)


def test_microsoft_sign_in_connects_at_once_with_nothing_left_to_ask(app):
    client = browser(app)
    cb = consent(client, start_web(client, MICROSOFT), "demo.microsoft@example.com")
    assert cb.headers["location"].endswith("signin=ok")
    user = user_row(app, "demo.microsoft@example.com")
    assert user.identity_provider == MICROSOFT and ":" in user.identity_subject  # tid:oid
    live = rows(app, OAuthConnection, user_id=user.id, revoked_at=None)
    assert [(r.provider, r.connection_name) for r in live] == [(MICROSOFT, MICROSOFT)]
    listing = client.get("/connections").json()
    assert wanted(client) == [] and {c["provider"]: c["connected"] for c in listing["connections"]}[MICROSOFT]


def test_the_role_ask_grants_one_set_and_stores_the_connection(app):
    client = browser(app)
    sign_in(client)
    go, cb = connect(client, "mail_send", "demo@example.com")
    assert "hint=demo%40example.com" in go.headers["location"]  # login_hint: the signed-in account
    assert query_of(cb) == {"connection": "connected", "provider": GOOGLE}
    by_id = {s["id"]: s["granted"] for s in wanted(client)}
    assert by_id == {"mail_send": True, "calendar": False}
    live = rows(app, OAuthConnection, revoked_at=None)
    assert len(live) == 1 and live[0].connection_name == GOOGLE and live[0].user_id == user_row(app, "demo@example.com").id
    connect(client, "calendar", "demo@example.com")
    assert all(s["granted"] for s in wanted(client))  # the second ask kept the first grant


def test_a_declined_ask_is_reported_and_the_set_stays_wanted(app):
    client = browser(app)
    sign_in(client)
    _, denied = connect(client, "mail_send", "demo@example.com", action="deny")
    assert query_of(denied) == {"connection": "error", "provider": GOOGLE, "reason": "consent_declined"}
    _, unticked = connect(client, "mail_send", "demo@example.com", ticked=())
    assert query_of(unticked)["reason"] == "consent_declined"
    assert rows(app, OAuthConnection, revoked_at=None) == []  # nothing stored, as on the native path
    assert not {c["provider"]: c["connected"] for c in client.get("/connections").json()["connections"]}[GOOGLE]
    assert [s["granted"] for s in wanted(client)] == [False, False]
    _, granted = connect(client, "mail_send", "demo@example.com")
    assert query_of(granted)["connection"] == "connected"


def test_the_ask_is_bound_to_the_account_that_signed_in(app):
    client = browser(app)
    sign_in(client)
    _, cb = connect(client, "mail_send", "viewer@example.com")  # consents with another account
    assert query_of(cb) == {"connection": "error", "provider": GOOGLE, "reason": "account_mismatch"}
    assert rows(app, OAuthConnection) == []


def test_a_set_the_role_does_not_want_is_refused(app):
    client = browser(app)
    sign_in(client)
    for bad in ("nope", "..", ""):
        reply = client.get(f"/connections/{GOOGLE}/start", params={"set": bad, "redirect_to": CONNECTIONS_PAGE})
        assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_request", bad
    crew = browser(app)
    sign_in(crew, "crew@example.com")
    assert crew.get(f"/connections/{GOOGLE}/start", params={"set": "mail_send"}).status_code == 403


def test_revoke_all_ends_every_session(app):
    client = browser(app)
    sign_in(client)
    done = client.post("/auth/sessions/revoke-all", headers=ORIGIN)
    assert done.status_code == 200 and done.json()["revoked"] >= 1
    assert client.get("/auth/me").status_code == 401


def test_break_glass_is_404_without_the_flag_and_only_for_flagged_rows(app, tmp_path, monkeypatch):
    client = browser(app)
    assert client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"}).status_code == 404
    assert client.get("/auth/providers").json()["break_glass"] is False
    monkeypatch.setenv("SDK_EXAMPLE_BREAKGLASS", "1")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/bg.db")
    flagged = browser(create_app())
    with session_scope(flagged.app.state.session_factory) as session:
        session.execute(User.__table__.update().where(User.email == "demo@example.com").values(allow_password=True))
    assert flagged.get("/auth/providers").json()["break_glass"] is True
    refused = flagged.post("/auth/firebase", json={"id_token": "mock:crew@example.com"}, headers=ORIGIN)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "provider_not_allowed"  # no flag on crew
    ok = flagged.post("/auth/firebase", json={"id_token": "mock:demo@example.com"}, headers=ORIGIN)
    assert ok.status_code == 200 and flagged.get("/auth/me").status_code == 200
    assert {r.provider for r in rows(flagged.app, AuthSession)} == {"password"}


def test_well_known_files_are_404_without_env_and_json_with_it(app, tmp_path, monkeypatch):
    monkeypatch.delenv("BOND_APPLE_APP_IDS", raising=False)
    monkeypatch.delenv("BOND_ANDROID_APPS", raising=False)
    empty = TestClient(create_app())
    for name in ("apple-app-site-association", "assetlinks.json"):
        assert empty.get(f"/.well-known/{name}").status_code == 404
    monkeypatch.setenv("BOND_APPLE_APP_IDS", "ABCDE12345.org.example.app")
    monkeypatch.setenv("BOND_ANDROID_APPS", "org.example.app=AA:BB:CC;DD:EE:FF")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/wk.db")
    full = TestClient(create_app())
    aasa = full.get("/.well-known/apple-app-site-association")
    assert aasa.headers["content-type"].startswith("application/json")
    assert aasa.json()["applinks"]["details"][0]["appIDs"] == ["ABCDE12345.org.example.app"]
    links = full.get("/.well-known/assetlinks.json").json()
    assert links[0]["target"]["package_name"] == "org.example.app"
    assert links[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB:CC", "DD:EE:FF"]


def test_providers_payload_has_the_fixture_shape(app):
    served = TestClient(app).get("/auth/providers").json()
    fixture = json.loads((FIXTURES / "providers_payload.json").read_text())
    assert set(fixture) <= set(served)
    assert served["signin"] and all(set(item) == set(fixture["signin"][0]) for item in served["signin"])
    assert served["default_flow"] == "signin"


def test_a_fake_provider_is_refused_at_startup_outside_fake_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", "a-test-secret-that-is-at-least-32-bytes-long")
    monkeypatch.setenv("SDK_EXAMPLE_PUBLIC_BASE", "https://api.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_REDIRECT_ALLOWLIST", "https://app.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_CORS_ORIGINS", "https://app.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/r.db")
    monkeypatch.setenv("SDK_EXAMPLE_SIGNIN_PROVIDERS", "fake-google")
    with pytest.raises(RuntimeError, match="fake"):
        create_app()


def test_the_seeds_match_the_fixture_and_nobody_invited_the_uninvited(app):
    fixture = json.loads((FIXTURES / "seed_identities.json").read_text())["identities"]
    invited = {i["email"]: i for i in fixture if i["invited"]}
    seeded = {row["email"]: row for row in DEMO_USERS}
    assert set(invited) == set(seeded)
    assert all(invited[e]["capabilities"] == seeded[e]["capabilities"] for e in seeded)
    with session_scope(app.state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(User).where(User.email == "uninvited@example.com")) == 0
    assert {i["email"] for i in fixture if not i["invited"]} == {"uninvited@example.com"}


def test_unticking_the_ask_keeps_an_earlier_grant(app):
    client = browser(app)
    sign_in(client)
    connect(client, "mail_send", "demo@example.com")
    _, again = connect(client, "calendar", "demo@example.com", ticked=())
    assert query_of(again)["reason"] == "consent_declined"
    assert {s["id"]: s["granted"] for s in wanted(client)} == {"mail_send": True, "calendar": False}


def test_losing_the_capability_between_start_and_callback_stores_nothing(app):
    from sdk_example.db import session_scope as scope

    client = browser(app)
    sign_in(client)
    started = client.get(f"/connections/{GOOGLE}/start", params={"set": "mail_send", "redirect_to": CONNECTIONS_PAGE})
    state = state_in(client.get(started.json()["url"]).headers["location"])
    with scope(app.state.session_factory) as session:
        session.query(User).filter_by(email="demo@example.com").update({"capabilities": []})
    cb = consent(client, state, "demo@example.com", shown=("mail_send",), ticked=("mail_send",))
    assert cb.status_code in (302, 403)
    if cb.status_code == 302:
        assert query_of(cb)["reason"] == "forbidden"
    assert rows(app, OAuthConnection) == []
    assert client.get(started.json()["url"]).status_code == 403  # /go refuses too


def test_a_database_behind_head_stops_startup_with_a_clear_message(tmp_path, monkeypatch):
    from alembic.config import Config

    from alembic import command

    url = f"sqlite:///{tmp_path}/old.db"
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", url)
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(config, "0002")
    with pytest.raises(RuntimeError, match="database at 0002; run make migrate"):
        create_app()


def test_fake_mode_on_a_public_https_address_is_refused_unless_allowed(monkeypatch):
    from sdk_example.settings import Settings

    monkeypatch.setenv("SDK_EXAMPLE_PUBLIC_BASE", "https://demo.example.org")
    with pytest.raises(RuntimeError, match="anyone sign in"):
        Settings.from_env()
    monkeypatch.setenv("SDK_EXAMPLE_ALLOW_FAKE_PUBLIC", "1")
    assert Settings.from_env().public_base == "https://demo.example.org"


def test_the_password_form_is_offered_only_with_break_glass(app, tmp_path, monkeypatch):
    assert TestClient(app).get("/auth/providers").json()["email_password"] is False
    monkeypatch.setenv("SDK_EXAMPLE_BREAKGLASS", "1")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/ep.db")
    assert TestClient(create_app()).get("/auth/providers").json()["email_password"] is True


def test_break_glass_form_sign_in_is_for_the_seeded_owner_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_BREAKGLASS", "1")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/owner.db")
    client = browser(create_app())
    owner = client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"}, headers=ORIGIN)
    assert owner.status_code == 200 and owner.json()["user"]["email"] == "demo@example.com"
    crew = browser(client.app).post("/auth/firebase", json={"id_token": "mock:crew@example.com"}, headers=ORIGIN)
    assert crew.status_code == 403 and crew.json()["detail"]["code"] == "provider_not_allowed"


def test_a_cookie_authenticated_mutation_needs_an_allowed_origin(app):
    client = TestClient(app, follow_redirects=False)  # no default Origin
    sign_in(client)
    evil = client.delete(f"/connections/{GOOGLE}", headers={"Origin": "https://evil.test"})
    assert evil.status_code == 403 and evil.json()["detail"]["code"] == "invalid_origin"
    assert client.delete(f"/connections/{GOOGLE}").status_code == 403  # no Origin at all
    assert client.delete(f"/connections/{GOOGLE}", headers=ORIGIN).status_code == 200
    token = client.post("/auth/refresh", json={}, headers=ORIGIN).json()["token"]
    bearer_only = TestClient(app)  # a phone: bearer, no cookie, no Origin
    assert bearer_only.delete(f"/connections/{GOOGLE}", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_the_daily_prune_job_deletes_spent_codes_and_dead_sessions(app):
    from datetime import UTC, datetime, timedelta

    from sdk_example.models.handoffs import OAuthHandoff

    client = browser(app)
    sign_in(client)
    client.post("/auth/logout", json={}, headers=ORIGIN)  # a revoked session row
    stack = app.state.signin
    with session_scope(app.state.session_factory) as session:
        stack.handoffs.issue(session, purpose="signin", provider=GOOGLE, payload={"user_id": "x"},
                             device_hash="0" * 64, attempt_id=None)
    assert len(rows(app, AuthSession)) == 1 and len(rows(app, OAuthHandoff)) == 1
    now = datetime.now(UTC)
    demo = TestClient(app, headers=ORIGIN)
    token = demo.post("/auth/demo", json={"user_id": "demo-user-1"}).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    ticker = demo.post  # any signed-in user may tick in fake mode
    ticker("/jobs/tick", json={"now": (now + timedelta(days=10)).isoformat()}, headers=auth)  # enqueues, due next day
    ran = ticker("/jobs/tick", json={"now": (now + timedelta(days=12)).isoformat()}, headers=auth).json()["ran"]
    assert [r["job_type"] for r in ran] == ["signin_prune"] and ran[0]["status"] == "done"
    assert rows(app, OAuthHandoff) == []
    assert [r.provider for r in rows(app, AuthSession)] == ["demo"]  # the logged-out google row is gone, demo's is live


def test_a_phone_connect_needs_an_account_bound_by_sign_in(app):
    client = TestClient(app, headers=ORIGIN)
    h = {"Authorization": "Bearer " + client.post("/auth/demo", json={"user_id": "demo-user-1"}).json()["token"]}
    reply = client.get(f"/connections/{GOOGLE}/start", headers=h, params={
        "mode": "native", "device_challenge": "0" * 64, "attempt": "a"})
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "invalid_request"


def test_connect_at_another_provider_than_the_sign_in_one_is_refused_without_a_policy_set(app):
    client = browser(app)
    sign_in(client)  # bound to fake-google
    reply = client.get(f"/connections/{MICROSOFT}/start", params={"redirect_to": CONNECTIONS_PAGE})
    assert reply.status_code == 400 and "sign-in account" in reply.json()["detail"]["message"]
    assert client.get(f"/connections/{GOOGLE}/start", params={"redirect_to": CONNECTIONS_PAGE}).status_code == 200


def test_find_invite_compares_the_stored_address_lowercased(app):
    from sdk_example.db import session_scope as scope

    with scope(app.state.session_factory) as session:
        session.query(User).filter_by(email="crew@example.com").update({"email": "CREW@example.com"})
    client = browser(app)
    assert sign_in(client, "crew@example.com").headers["location"].endswith("signin=ok")


def test_provider_alive_maps_only_a_provider_refusal_to_false(app):
    from sdk_example.directory import Directory

    client = browser(app)
    consent(client, start_web(client, MICROSOFT), "demo.microsoft@example.com")
    wiring, fake = app.state.oauth, app.state.oauth.fakes[MICROSOFT]
    directory = Directory(wiring, fake=False)  # the real-mode branch, over the fake provider
    import bond_oauth as oauth

    with session_scope(app.state.session_factory) as session:
        user = session.query(User).filter_by(email="demo.microsoft@example.com").one()
        row = session.query(OAuthConnection).filter_by(user_id=user.id, revoked_at=None).one()
        assert directory.provider_alive(session, user, MICROSOFT) is True
        oauth.forget_access(row.id)
        fake.fail_refresh_with("invalid_grant")
        try:
            assert directory.provider_alive(session, user, MICROSOFT) is False
        finally:
            fake.fail_refresh_with(None)
        row.last_error = None
        row.refresh_token_enc = "tampered"  # our storage problem, not the provider's verdict
        oauth.forget_access(row.id)
        assert directory.provider_alive(session, user, MICROSOFT) is None


def test_the_consent_page_escapes_the_hint_and_the_state(app):
    client = browser(app)
    state = start_web(client)
    page = client.get("/connections/fake/consent", params={"state": state, "hint": '"><script>x()</script>'})
    assert page.status_code == 200 and "<script>x()" not in page.text and "&lt;script&gt;" in page.text
    assert f"value='{state}'" in page.text  # a valid state is plain base64 text, rendered inside quotes


def test_session_issuing_routes_need_an_allowed_origin_for_cookie_delivery(app, tmp_path, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_BREAKGLASS", "1")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/lc.db")
    client = TestClient(create_app())  # signed out, no default Origin
    demo, firebase = ("/auth/demo", {"user_id": "demo-user-1"}), ("/auth/firebase", {"id_token": "mock:demo@example.com"})
    for path, body in (demo, firebase):
        for origin in ({"Origin": "https://evil.test"}, {}):
            refused = client.post(path, json=body, headers=origin)
            assert refused.status_code == 403 and refused.json()["detail"]["code"] == "invalid_origin", (path, origin)
            assert not refused.headers.get_list("set-cookie")
        ok = client.post(path, json=body, headers=ORIGIN)
        assert ok.status_code == 200 and len(ok.headers.get_list("set-cookie")) == 2, path
        phone = TestClient(create_app()).post(path, json={**body, "delivery": "body"})  # no Origin needed
        assert phone.status_code == 200 and phone.json()["refresh_token"] and not phone.headers.get_list("set-cookie")


def test_sign_in_works_without_the_connections_module(tmp_path, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_CONNECTIONS", "0")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/noconn.db")
    client = browser(create_app())
    assert sign_in(client).headers["location"].endswith("signin=ok")  # identity-only, no connection table needed
    assert client.get("/auth/me").status_code == 200
    assert client.get("/connections").status_code == 404
    assert client.get(f"/connections/{GOOGLE}/start").status_code == 404


def test_a_custom_prefix_moves_the_routes_and_the_link_files_together(tmp_path, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_SIGNIN_PREFIX", "/api/v1/auth")
    monkeypatch.setenv("BOND_APPLE_APP_IDS", "ABCDE12345.org.example.app")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/prefix.db")
    client = browser(create_app())
    aasa = client.get("/.well-known/apple-app-site-association").json()
    assert aasa["applinks"]["details"][0]["components"] == [{"/": "/api/v1/app/return/*"}]
    assert client.get(f"/api/v1/app/return/{GOOGLE}").status_code == 200  # where the files point
    started = client.post(f"/api/v1/auth/signin/{GOOGLE}/start", json={"redirect_to": "http://localhost:8078/auth"},
                          headers=ORIGIN)
    assert started.status_code == 200
    cb = consent(client, state_in(started.json()["url"]), "demo@example.com")
    assert cb.headers["location"].endswith("signin=ok")  # the fake consent page followed the prefix
    assert client.post("/api/v1/auth/refresh", json={}, headers=ORIGIN).status_code == 200
    assert client.delete(f"/connections/{GOOGLE}", headers={"Origin": "https://evil.test"}).status_code == 403
