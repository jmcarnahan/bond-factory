"""E-signing on the example: assets, auth, fake mode, the job's retry, form limits."""

from bond_esign import asset_names
from connections_util import headers
from esign_util import demo, evidence, kinds, post, tick, typed_form
from fastapi.testclient import TestClient

from sdk_example.esign_wiring import TABLES


def test_the_static_assets_are_served_and_nothing_else(client):
    types = {"bond-esign.css": "text/css", "bond-esign.js": "text/javascript",
             "signature_pad.umd.min.js": "text/javascript", "LICENSE-signature_pad": "text/plain"}
    for name in asset_names():
        reply = client.get(f"/esign/static/{name}")
        assert reply.status_code == 200 and reply.headers["content-type"].startswith(types[name]), name
    for bad in ("nope.js", "..%2Fsettings.py", "bond-esign.CSS"):
        assert client.get(f"/esign/static/{bad}").status_code == 404


def test_the_page_links_only_the_served_assets(client):
    page = client.get(demo(client)["sign_url"]).text
    for name in ("bond-esign.css", "signature_pad.umd.min.js", "bond-esign.js"):
        assert f"/esign/static/{name}" in page


def test_the_evidence_export_is_staff_only(client):
    created = demo(client)
    path = f"/esign/requests/{created['request_id']}/evidence"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(client, "demo-user-2")).status_code == 403  # the viewer has no capability
    assert client.get(path, headers=headers(client)).status_code == 200
    assert client.get("/esign/requests/none/evidence", headers=headers(client)).status_code == 404


def test_the_demo_routes_are_404_outside_fake_mode(app, tmp_path, monkeypatch):
    app.state.settings = app.state.settings.__class__(**{**app.state.settings.__dict__, "mode": "real"})
    client = TestClient(app)
    assert client.post("/esign/demo", json={}).status_code == 404
    assert client.post("/esign/demo/x/void").status_code == 404


def test_the_demo_refuses_a_request_nobody_can_sign(client):
    reply = client.post("/esign/demo", json={"allow_typed": False, "allow_drawn": False})
    assert reply.status_code == 422 and "invalid_demo" in reply.text
    assert client.post("/esign/demo", json={"surprise": 1}).status_code == 422


def test_form_limits(client):
    created = demo(client)
    big = client.post(created["sign_url"], content=b"x=" + b"a" * 500_000,
                      headers={"content-type": "application/x-www-form-urlencoded"})
    assert big.status_code == 413
    plain = client.post(created["sign_url"], json={"typed_name": "x"})
    assert plain.status_code == 415
    bad_png = post(client, created, typed_form(mode="drawn", drawn_png="data:image/png;base64,AAAA"))
    assert bad_png.headers["location"].endswith("?error=signature_invalid")
    assert kinds(client, created) == ["created", "token_issued"]  # none of the refused posts wrote an event


def test_the_job_handler_retried_leaves_one_completed_event(client, app):
    created = demo(client)
    post(client, created, typed_form())
    tick(client)
    first = evidence(client, created)
    handler = app.state.job_registry.get("esign_complete")
    now = app.state.clock.utcnow_naive()
    from sdk_example.db import session_scope

    for _ in range(2):
        with session_scope(app.state.session_factory) as session:
            result = handler(session, {"request_id": created["request_id"]}, now)
            assert result["skipped"] is True  # the tick already completed it: nothing is built or stored again
    again = evidence(client, created)
    assert [e["kind"] for e in again["events"]].count("completed") == 1
    assert [e["kind"] for e in again["events"]].count("document_built") == 1
    assert again["request"]["signed_sha256"] == first["request"]["signed_sha256"]
    assert again["check"]["ok"]


def test_the_job_skips_a_voided_request(client, app):
    from sdk_example.db import session_scope

    created = demo(client)
    assert client.post(f"/esign/demo/{created['request_id']}/void").json()["status"] == "voided"
    handler = app.state.job_registry.get("esign_complete")
    with session_scope(app.state.session_factory) as session:
        assert handler(session, {"request_id": created["request_id"]}, app.state.clock.utcnow_naive())["skipped"]
        assert handler(session, {"request_id": "gone"}, app.state.clock.utcnow_naive())["skipped"]


def test_a_signed_request_cannot_be_voided_before_the_job_runs(client):
    created = demo(client)
    post(client, created, typed_form())
    assert client.post(f"/esign/demo/{created['request_id']}/void").status_code == 409


def test_the_tables_match_the_library_contract(app):
    from sqlalchemy import inspect

    names = set(inspect(app.state.engine).get_table_names())
    assert {"esign_requests", "esign_signers", "esign_events"} <= names
    assert TABLES.request.__tablename__ == "esign_requests"


def test_the_signing_page_has_an_empty_icon_so_no_favicon_request_fails(client):
    created = demo(client)
    assert '<link rel="icon" href="data:,">' in client.get(created["sign_url"]).text
    assert '<link rel="icon" href="data:,">' in client.get("/esign/sign/not-a-token").text


def test_the_tick_expires_an_overdue_open_request_once(client):
    created = demo(client, expires_in_seconds=-60)
    assert kinds(client, created) == ["created", "token_issued"]
    ran = tick(client, "2030-01-01T00:00:00Z")
    assert "ran" in ran
    assert kinds(client, created).count("expired") == 1
    assert evidence(client, created)["request"]["status"] == "expired"
    tick(client, "2030-01-01T01:00:00Z")  # a second pass writes nothing more
    assert kinds(client, created).count("expired") == 1
