from urllib.parse import parse_qs, urlsplit

import pytest
from connections_util import APP, begin, connect, headers, start, state_of, statuses
from fastapi.testclient import TestClient

from sdk_example.models.auth import VIEWER_USER_ID
from sdk_example.models.connections import OAuthConnection


def test_requires_a_session(client):
    assert client.get("/connections").status_code == 401
    assert client.get("/connections/fake-google/start").status_code == 401


def test_lists_both_providers_disconnected(client):
    rows = statuses(client, headers(client))
    assert set(rows) == {"fake-google", "fake-microsoft"} and not any(r["connected"] for r in rows.values())


def test_start_go_consent_callback_then_connected(client):
    h = headers(client)
    reply = connect(client, h)
    assert reply.status_code == 302
    location = urlsplit(reply.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == APP
    assert parse_qs(location.query) == {"connection": ["connected"], "provider": ["fake-google"]}
    row = statuses(client, h)["fake-google"]
    assert row["connected"] and row["email"] == "demo.google@example.com" and not row["needs_reconnect"]
    assert row["scopes"] and row["connected_at"].endswith("Z")


def test_start_url_is_an_absolute_go_url(client):
    url = start(client, headers(client))
    assert url.startswith("http://testserver/connections/fake-google/go?state=")


def test_start_without_redirect_uses_the_first_allowed_origin(client):
    h = headers(client)
    go_url = client.get("/connections/fake-google/start", headers=h).json()["url"]
    go = client.get(go_url, headers=h, follow_redirects=False)
    reply = client.get("/connections/fake-google/callback", headers=h, follow_redirects=False,
                       params={"state": state_of(go.headers["location"]), "code": "mock"})
    assert reply.headers["location"].startswith("http://localhost:8078/connections?")


@pytest.mark.parametrize("target", [
    "https://evil.example.org/x", "http://localhost:9999/connections", "javascript:alert(1)",
    "http://localhost:8078" + chr(64) + "evil.example.org/", "//evil.example.org", "http:\\\\evil.example.org",
])
def test_disallowed_redirect_is_400(client, target):
    reply = client.get("/connections/fake-google/start", params={"redirect_to": target}, headers=headers(client))
    assert reply.status_code == 400 and reply.json()["detail"]["code"] == "redirect_not_allowed"


def test_empty_allowlist_refuses_every_redirect_with_400(tmp_path, monkeypatch):
    from sdk_example.main import create_app

    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/e.db")
    monkeypatch.setenv("SDK_EXAMPLE_REDIRECT_ALLOWLIST", "")
    c = TestClient(create_app())
    h = headers(c)
    for params in ({}, {"redirect_to": APP}):
        reply = c.get("/connections/fake-google/start", params=params, headers=h)
        assert reply.status_code == 400 and reply.json()["detail"]["code"] == "redirect_not_allowed"


def test_unknown_provider_is_404(client):
    reply = client.get("/connections/nope/start", params={"redirect_to": APP}, headers=headers(client))
    assert reply.status_code == 404 and reply.json()["detail"]["code"] == "unknown_provider"


def test_provider_error_redirects_with_error(client):
    h = headers(client)
    state = begin(client, h)
    reply = client.get("/connections/fake-google/callback", params={"state": state, "error": "access_denied"},
                       headers=h, follow_redirects=False)
    query = parse_qs(urlsplit(reply.headers["location"]).query)
    assert reply.status_code == 302 and query["connection"] == ["error"] and query["reason"] == ["consent_declined"]  # the provider error access_denied, as the shared code
    assert not statuses(client, h)["fake-google"]["connected"]


def test_wrong_code_redirects_with_error(client):
    h = headers(client)
    state = begin(client, h)
    reply = client.get("/connections/fake-google/callback", params={"state": state, "code": "bad"}, headers=h,
                       follow_redirects=False)
    assert parse_qs(urlsplit(reply.headers["location"]).query)["connection"] == ["error"]


def test_simulate_expiry_then_needs_reconnect_then_reconnect(client):
    h = headers(client)
    connect(client, h)
    reply = client.post("/connections/fake-google/simulate-expiry", headers=h)
    assert reply.status_code == 200 and reply.json()["needs_reconnect"] is True
    row = statuses(client, h)["fake-google"]
    assert row["connected"] and row["needs_reconnect"]
    connect(client, h)
    assert not statuses(client, h)["fake-google"]["needs_reconnect"]


def test_simulate_expiry_needs_a_connection(client):
    reply = client.post("/connections/fake-google/simulate-expiry", headers=headers(client))
    assert reply.status_code == 404 and reply.json()["detail"]["code"] == "not_connected"


def test_disconnect(client):
    h = headers(client)
    connect(client, h)
    reply = client.delete("/connections/fake-google", headers=h)
    assert reply.status_code == 200 and reply.json()["connected"] is False
    assert not statuses(client, h)["fake-google"]["connected"]


def test_two_providers_are_independent(client):
    h = headers(client)
    connect(client, h, "fake-google")
    connect(client, h, "fake-microsoft")
    client.delete("/connections/fake-google", headers=h)
    rows = statuses(client, h)
    assert not rows["fake-google"]["connected"] and rows["fake-microsoft"]["connected"]
    client.post("/connections/fake-microsoft/simulate-expiry", headers=h)
    rows = statuses(client, h)
    assert rows["fake-microsoft"]["needs_reconnect"] and not rows["fake-google"]["needs_reconnect"]


def test_connections_belong_to_the_session_user(client):
    h1, h2 = headers(client), headers(client, VIEWER_USER_ID)
    connect(client, h1)
    assert statuses(client, h1)["fake-google"]["connected"]
    assert not statuses(client, h2)["fake-google"]["connected"]


def test_viewer_without_capability_gets_403_on_mutating_routes(client):
    h = headers(client, VIEWER_USER_ID)
    calls = [
        client.get("/connections/fake-google/start", params={"redirect_to": APP}, headers=h),
        client.delete("/connections/fake-google", headers=h),
        client.post("/connections/fake-google/simulate-expiry", headers=h),
    ]
    assert [c.status_code for c in calls] == [403, 403, 403]
    assert all(c.json()["detail"]["code"] == "forbidden" for c in calls)


def test_viewer_can_still_list(client):
    assert client.get("/connections", headers=headers(client, VIEWER_USER_ID)).status_code == 200


def test_tokens_are_stored_encrypted(client, app):
    connect(client, headers(client))
    with app.state.session_factory() as session:
        row = session.query(OAuthConnection).one()
        assert "fake-" not in row.refresh_token_enc and "fake-" not in (row.access_token_enc or "")


def test_fake_routes_absent_in_real_mode(tmp_path, monkeypatch):
    from sdk_example.main import create_app

    monkeypatch.setenv("SDK_EXAMPLE_MODE", "real")
    monkeypatch.setenv("SDK_EXAMPLE_AUTH_SECRET", "x" * 40)
    monkeypatch.setenv("SDK_EXAMPLE_PUBLIC_BASE", "https://api.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_REDIRECT_ALLOWLIST", "https://app.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_CORS_ORIGINS", "https://app.example.org")
    monkeypatch.setenv("SDK_EXAMPLE_DATABASE_URL", f"sqlite:///{tmp_path}/r.db")
    other = TestClient(create_app())
    assert other.get("/connections/fake/consent", params={"state": "s"}).status_code in (404, 422)
    assert other.post("/connections/google/simulate-expiry").status_code in (401, 404, 405)
