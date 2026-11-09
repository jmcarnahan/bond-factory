import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from bond_auth_py import create_access_token
from fastapi import Depends
from fastapi.testclient import TestClient

from sdk_example.auth_dep import COOKIE, require_capability
from sdk_example.db import session_scope
from sdk_example.main import create_app
from sdk_example.models.auth import User, utcnow

STRONG_SECRET = "a-test-secret-that-is-at-least-32-bytes-long"


def demo(client: TestClient, user_id: str = "demo-user-1") -> dict:
    response = client.post("/auth/demo", json={"user_id": user_id})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def code_of(response) -> str:
    return response.json()["detail"]["code"]


def edit_user(app, user_id: str, **values) -> None:
    with session_scope(app.state.session_factory) as session:
        user = session.get(User, user_id)
        for key, value in values.items():
            setattr(user, key, value)


def read_user(app, user_id: str) -> User:
    with session_scope(app.state.session_factory) as session:
        return session.get(User, user_id)


def test_demo_sign_in_returns_token_and_user(client):
    body = demo(client)
    assert body["user"] == {
        "id": "demo-user-1", "email": "demo@example.com", "name": "Demo User", "initials": "DU",
        "language": "en", "capabilities": ["tasks.write", "connections.manage"],
    }
    me = client.get("/auth/me", headers=bearer(body["token"]))
    assert me.status_code == 200
    assert me.json()["user"]["id"] == "demo-user-1"


def test_demo_unknown_user_is_404_and_empty_body_is_422(client):
    assert client.post("/auth/demo", json={"user_id": "nobody"}).status_code == 404
    response = client.post("/auth/demo", json={})
    assert response.status_code == 422
    assert code_of(response) == "validation_error"


def test_demo_route_is_404_outside_fake_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/real.db")
    real = TestClient(create_app())
    assert real.post("/auth/demo", json={"user_id": "demo-user-1"}).status_code == 404
    answer = real.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    assert answer.status_code == 501
    assert code_of(answer) == "firebase_not_configured"
    providers = real.get("/auth/providers").json()
    assert providers["demo"] is False and providers["mock"] is False


def test_mock_firebase_sign_in_links_the_identity(app, client):
    answer = client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["user"]["id"] == "demo-user-1"
    user = read_user(app, "demo-user-1")
    assert user.firebase_uid == "mock-uid-1"
    assert user.accepted_at is not None and user.last_sign_in_at is not None
    assert client.post("/auth/firebase", json={"id_token": "mock:DEMO@example.com"}).status_code == 200


def test_not_invited_is_403_with_the_error_body(client):
    answer = client.post("/auth/firebase", json={"id_token": "mock:notinvited@example.com"})
    assert answer.status_code == 403
    assert answer.json() == {"detail": {"code": "not_invited", "message": "This address was not invited."}}


def test_a_different_identity_on_a_linked_address_is_refused(app, client):
    edit_user(app, "demo-user-1", firebase_uid="someone-else")
    answer = client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    assert answer.status_code == 403
    assert code_of(answer) == "identity_mismatch"


def test_an_unverifiable_token_is_401_invalid_token(client):
    answer = client.post("/auth/firebase", json={"id_token": "garbage"})
    assert answer.status_code == 401
    assert code_of(answer) == "invalid_token"


def test_refresh_renews_without_counting_a_sign_in(app, client):
    client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    before = read_user(app, "demo-user-1").last_sign_in_at
    answer = client.post("/auth/refresh", json={"id_token": "mock:demo@example.com"})
    assert answer.status_code == 200
    assert answer.json()["token"]
    assert read_user(app, "demo-user-1").last_sign_in_at == before


def test_revoked_sessions_are_401_and_block_old_id_tokens(app, client):
    token = demo(client)["token"]
    assert client.get("/auth/me", headers=bearer(token)).status_code == 200
    edit_user(app, "demo-user-1", sessions_valid_after=utcnow() + timedelta(seconds=60))
    me = client.get("/auth/me", headers=bearer(token))
    assert me.status_code == 401
    assert code_of(me) == "session_revoked"
    exchange = client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    assert exchange.status_code == 401
    assert code_of(exchange) == "session_revoked"


def test_a_deactivated_user_is_403_everywhere(app, client):
    token = demo(client)["token"]
    edit_user(app, "demo-user-1", is_active=False)
    me = client.get("/auth/me", headers=bearer(token))
    assert me.status_code == 403 and code_of(me) == "deactivated"
    exchange = client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    assert exchange.status_code == 403 and code_of(exchange) == "deactivated"


def test_an_expired_token_is_401(app, client):
    old = datetime.now(UTC) - timedelta(days=30)
    token = create_access_token(sub="demo-user-1", name="Demo User", capabilities=[],
                                settings=app.state.auth_settings, now=old, ttl=timedelta(minutes=1))
    answer = client.get("/auth/me", headers=bearer(token))
    assert answer.status_code == 401 and code_of(answer) == "invalid_token"


def test_no_token_is_401(client):
    answer = client.get("/auth/me")
    assert answer.status_code == 401 and code_of(answer) == "invalid_token"


def test_the_cookie_works_and_an_explicit_bearer_wins_over_it(client):
    demo(client)
    assert COOKIE in client.cookies
    assert client.get("/auth/me").status_code == 200
    bad = client.get("/auth/me", headers=bearer("not-a-token"))
    assert bad.status_code == 401


def test_logout_clears_the_cookie(client):
    demo(client)
    answer = client.post("/auth/logout")
    assert answer.json() == {"status": "logged_out"}
    assert COOKIE not in client.cookies
    assert client.get("/auth/me").status_code == 401


def test_providers_has_the_merged_shape_in_fake_mode(client):
    assert client.get("/auth/providers").json() == {
        "demo": True, "email_password": True, "google": False, "google_web_client_id": None, "apple": False,
        "mock": True, "firebase": None, "sync": {"url": None},
    }


def test_me_language_patch(client):
    token = demo(client)["token"]
    answer = client.patch("/auth/me", json={"language": "es"}, headers=bearer(token))
    assert answer.status_code == 200 and answer.json()["user"]["language"] == "es"
    assert client.get("/auth/me", headers=bearer(token)).json()["user"]["language"] == "es"
    bad = client.patch("/auth/me", json={"language": "not a locale"}, headers=bearer(token))
    assert bad.status_code == 422 and code_of(bad) == "validation_error"


def test_firebase_and_refresh_are_limited_to_20_a_minute(client):
    for _ in range(20):
        assert client.post("/auth/firebase", json={"id_token": "garbage"}).status_code == 401
    limited = client.post("/auth/refresh", json={"id_token": "garbage"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert code_of(limited) == "rate_limited"


def test_require_capability_uses_the_users_row(app, client):
    needs_write = Depends(require_capability("tasks.write"))

    def guarded(who: Annotated[str, needs_write]) -> dict:
        return {"user": who}

    app.add_api_route("/_cap", guarded)
    owner = demo(client)["token"]
    viewer = demo(client, "demo-user-2")["token"]
    assert client.get("/_cap", headers=bearer(owner)).json() == {"user": "demo-user-1"}
    refused = client.get("/_cap", headers=bearer(viewer))
    assert refused.status_code == 403 and code_of(refused) == "forbidden"
    edit_user(app, "demo-user-1", capabilities=[])
    assert client.get("/_cap", headers=bearer(owner)).status_code == 403


def test_the_mock_identities_file_lists_the_three_addresses(app):
    path = app.state.out_dir / "mock_identities.json"
    emails = [row["email"] for row in json.loads(path.read_text())]
    assert emails == ["demo@example.com", "viewer@example.com", "notinvited@example.com"]


def test_the_example_starts_with_no_environment(client):
    assert client.get("/health").json() == {"status": "ok", "mode": "fake"}


def test_rate_limit_buckets_follow_the_last_forwarded_hop(client):
    def hit(prefix: str, last: str):
        return client.post("/auth/firebase", json={"id_token": "garbage"},
                           headers={"X-Forwarded-For": f"{prefix}, {last}"})

    for i in range(20):  # a spoofed first hop must not make a new bucket
        assert hit(f"10.0.0.{i}", "203.0.113.7").status_code == 401
    assert hit("10.9.9.9", "203.0.113.7").status_code == 429
    assert hit("10.0.0.1", "203.0.113.8").status_code == 401  # another last hop is another bucket


def test_firebase_with_sign_in_false_is_a_renewal(app, client):
    client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    before = read_user(app, "demo-user-1").last_sign_in_at
    answer = client.post("/auth/firebase", json={"id_token": "mock:demo@example.com", "sign_in": False})
    assert answer.status_code == 200, answer.text
    assert read_user(app, "demo-user-1").last_sign_in_at == before
    client.post("/auth/firebase", json={"id_token": "mock:demo@example.com", "sign_in": True})
    assert read_user(app, "demo-user-1").last_sign_in_at > before


def test_refresh_never_counts_as_a_sign_in_even_when_asked(app, client):
    client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})
    before = read_user(app, "demo-user-1").last_sign_in_at
    for body in ({}, {"sign_in": True}, {"sign_in": False}):
        answer = client.post("/auth/refresh", json={"id_token": "mock:demo@example.com", **body})
        assert answer.status_code == 200, answer.text
    assert read_user(app, "demo-user-1").last_sign_in_at == before


def test_session_cookie_attributes(client):
    for answer in (client.post("/auth/demo", json={"user_id": "demo-user-1"}),
                   client.post("/auth/firebase", json={"id_token": "mock:demo@example.com"})):
        cookie = answer.headers["set-cookie"].lower()
        assert cookie.startswith(f"{COOKIE}=")
        assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
        assert "secure" not in cookie  # fake mode is plain http on localhost


def test_session_cookie_is_secure_outside_fake_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", STRONG_SECRET)
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/real.db")
    real = create_app()
    from sdk_example.models.auth import ensure_demo_users
    from sdk_example.wiring import bootstrap_schema

    bootstrap_schema(real.state.engine)
    with session_scope(real.state.session_factory) as session:
        ensure_demo_users(session)
    from bond_auth_py import set_verifier

    set_verifier(lambda token: {"uid": "u1", "email": "demo@example.com", "auth_time": datetime.now(UTC).timestamp()})
    try:
        answer = TestClient(real).post("/auth/firebase", json={"id_token": "any"})
    finally:
        set_verifier(None)
    assert answer.status_code == 200, answer.text
    assert "secure" in answer.headers["set-cookie"].lower()


def test_revocation_is_answered_before_deactivation(app, client):
    token = demo(client)["token"]
    edit_user(app, "demo-user-1", is_active=False, sessions_valid_after=utcnow() + timedelta(seconds=60))
    answer = client.get("/auth/me", headers=bearer(token))
    assert answer.status_code == 401 and code_of(answer) == "session_revoked"


def test_a_token_issued_exactly_at_the_mark_is_accepted(app, client):
    issued = datetime.now(UTC)
    token = create_access_token(sub="demo-user-1", name="Demo User", capabilities=[],
                                settings=app.state.auth_settings, now=issued)
    edit_user(app, "demo-user-1", sessions_valid_after=issued.replace(tzinfo=None))
    assert client.get("/auth/me", headers=bearer(token)).status_code == 200  # strict: only iat < mark is revoked
    edit_user(app, "demo-user-1", sessions_valid_after=issued.replace(tzinfo=None) + timedelta(microseconds=1))
    assert client.get("/auth/me", headers=bearer(token)).status_code == 401


def test_normal_responses_carry_the_cors_header(client):
    answer = client.get("/health", headers={"Origin": "http://localhost:8078"})
    assert answer.headers["access-control-allow-origin"] == "http://localhost:8078"
    assert answer.headers["access-control-allow-credentials"] == "true"
    other = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
