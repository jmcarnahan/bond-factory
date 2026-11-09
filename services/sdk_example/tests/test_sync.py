import json
import re
from pathlib import Path

import jwt
import pytest

from sdk_example.models.auth import DEMO_USER_ID
from sdk_example.models.sync import Note

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "sync"
SYNC_URL = "http://sync.example.test"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def signed_in(client):
    body = client.post("/auth/demo", json={"user_id": DEMO_USER_ID}).json()
    client.headers["Authorization"] = f"Bearer {body['token']}"
    return client


@pytest.fixture
def sync_on(monkeypatch):
    monkeypatch.setenv("SDK_EXAMPLE_SYNC_URL", SYNC_URL)


def assert_validation_body(response):
    detail = response.json()["detail"]
    assert detail["code"] == "validation_error"
    assert isinstance(detail["errors"], list) and detail["errors"]
    assert {"loc", "msg", "type"} <= set(detail["errors"][0])


def seed_other_users_note(app, note_id="note-taken"):
    with app.state.session_factory() as session:
        session.add(Note(id=note_id, owner_user_id="someone-else", title="theirs"))
        session.commit()


def test_upload_requires_a_session(client):
    r = client.post("/sync/upload", json=fixture("upload_request_ok.json"))
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_token"


def test_mixed_fixture_through_the_real_route(app, signed_in):
    seed_other_users_note(app)
    r = signed_in.post("/sync/upload", json=fixture("upload_request_mixed.json"))
    assert r.status_code == 200
    expected = fixture("upload_response_mixed.json")
    assert r.json()["results"] == expected["results"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", r.json()["server_now"])
    with app.state.session_factory() as session:
        note = session.get(Note, "note-1")
        assert (note.owner_user_id, note.title) == (DEMO_USER_ID, "First note, edited")
        assert session.get(Note, "note-taken").owner_user_id == "someone-else"


def test_ok_fixture_applies_put_patch_delete(app, signed_in):
    r = signed_in.post("/sync/upload", json=fixture("upload_request_ok.json"))
    assert [x["status"] for x in r.json()["results"]] == ["ok"] * 4
    with app.state.session_factory() as session:
        assert session.get(Note, "note-2").deleted_at is not None
        assert session.get(Note, "note-1").deleted_at is None


def test_replayed_upload_is_safe(signed_in):
    body = fixture("upload_request_ok.json")
    first = signed_in.post("/sync/upload", json=body).json()["results"]
    second = signed_in.post("/sync/upload", json=body).json()["results"]
    assert first == [{"seq": i, "status": "ok"} for i in range(4)]
    assert [x["status"] for x in second] == ["ok", "ok", "ok", "skipped"]  # the put replays as ok, the delete is already done


def test_payload_cannot_choose_the_owner(app, signed_in):
    body = {"ops": [{"seq": 0, "op": "put", "table": "notes", "id": "n-1",
                     "data": {"title": "x", "owner_user_id": "someone-else"}}]}
    assert signed_in.post("/sync/upload", json=body).json()["results"] == [{"seq": 0, "status": "ok"}]
    with app.state.session_factory() as session:
        assert session.get(Note, "n-1").owner_user_id == DEMO_USER_ID


def test_duplicate_seq_is_422(signed_in):
    r = signed_in.post("/sync/upload", json=fixture("upload_request_dup_seq.json"))
    assert r.status_code == 422
    assert_validation_body(r)


def test_101_ops_is_422(signed_in):
    r = signed_in.post("/sync/upload", json=fixture("upload_request_too_many_ops.json"))
    assert r.status_code == 422
    assert_validation_body(r)


def test_bad_ids_are_verdicts_not_422(signed_in):
    ids = fixture("bad_ids.json")["invalid"]
    ops = [{"seq": i, "op": "put", "table": "notes", "id": bad, "data": {"title": "t"}} for i, bad in enumerate(ids)]
    r = signed_in.post("/sync/upload", json={"ops": ops})
    assert r.status_code == 200
    assert {x["code"] for x in r.json()["results"]} == {"invalid"}


def test_token_is_503_sync_off_without_a_url(signed_in):
    r = signed_in.post("/sync/token")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "sync_off"
    off = fixture("sync_token_claims.json")["off_response"]
    assert (r.status_code, r.json()["detail"]["code"]) == (off["status"], off["body"]["detail"]["code"])


def test_token_requires_a_session(sync_on, client):
    assert client.post("/sync/token").status_code == 401


def test_token_and_jwks_round_trip(sync_on, app, signed_in):
    r = signed_in.post("/sync/token")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"token", "expires_at", "endpoint", "server_now"}
    assert body["endpoint"] == SYNC_URL
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", body["expires_at"])
    assert (Path(app.state.out_dir) / "sync_key.pem").exists()

    keys = signed_in.get("/sync/jwks.json")
    assert keys.status_code == 200
    assert keys.headers["cache-control"] == "public, max-age=300"
    jwk = keys.json()["keys"][0]
    assert (jwk["kid"], jwk["alg"], jwk["use"]) == ("bond-sync-1", "ES256", "sig")
    public = jwt.algorithms.ECAlgorithm.from_jwk({k: jwk[k] for k in ("kty", "crv", "x", "y")})
    claims = jwt.decode(body["token"], public, algorithms=["ES256"], audience="powersync")
    assert claims["sub"] == DEMO_USER_ID
    assert claims["exp"] - claims["iat"] == 900


def test_key_is_generated_once_and_reused(sync_on, app, signed_in):
    first = signed_in.get("/sync/jwks.json").json()
    second = signed_in.get("/sync/jwks.json").json()
    assert first == second


def test_jwks_is_public_and_404_when_off(client, signed_in):
    anonymous = type(client)(client.app)
    r = anonymous.get("/sync/jwks.json")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_jwks_needs_no_session_when_on(sync_on, client):
    assert client.get("/sync/jwks.json").status_code == 200


def test_database_down_answers_503_with_retry_after(signed_in, monkeypatch):
    from bond_sync_py import DbUnavailable

    from sdk_example.routes import sync as sync_routes

    def down(*args, **kwargs):
        raise DbUnavailable("down")

    monkeypatch.setattr(sync_routes, "upload", down)
    r = signed_in.post("/sync/upload", json=fixture("upload_request_ok.json"))
    assert r.status_code == 503
    assert r.headers["retry-after"] == "5"
    assert r.json()["detail"]["code"] == "db_unavailable"
