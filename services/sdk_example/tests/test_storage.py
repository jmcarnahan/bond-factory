from datetime import timedelta

from fastapi.testclient import TestClient

from sdk_example.db import session_scope
from sdk_example.models.auth import utcnow
from sdk_example.models.grants import DownloadGrant

PDF = b"%PDF-1.4 example bytes"


def signed_in(app, user_id: str = "demo-user-1") -> TestClient:
    who = TestClient(app)
    assert who.post("/auth/demo", json={"user_id": user_id}).status_code == 200
    return who


def upload(who: TestClient, content: bytes = PDF, name: str = "report.pdf", kind: str = "application/pdf"):
    return who.post("/documents", files={"file": (name, content, kind)})


def share(who: TestClient, document_id: str, **body):
    response = who.post(f"/documents/{document_id}/share", json=body or None)
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_returns_the_document_and_stores_the_bytes(app):
    who = signed_in(app)
    response = upload(who)
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["filename"] == "report.pdf"
    assert document["content_type"] == "application/pdf"
    assert document["kind"] == "file"
    assert document["owner_user_id"] == "demo-user-1"
    stored = app.state.storage.download_bytes(f"documents/demo-user-1/{document['id']}")
    assert stored == PDF
    assert who.get(f"/documents/{document['id']}").json() == document


def test_upload_needs_a_session_and_a_sane_file(app):
    assert upload(TestClient(app)).status_code == 401
    who = signed_in(app)
    assert upload(who, content=b"").json()["detail"]["code"] == "empty_file"
    assert upload(who, content=b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    sneaky = upload(who, name="../../etc/passwd", kind="text/plain")
    assert sneaky.status_code == 201 and sneaky.json()["filename"] == "passwd"
    assert upload(who, name="p.png", kind="image/png").json()["kind"] == "image"


def test_someone_elses_document_looks_missing(app):
    owner, other = signed_in(app), signed_in(app, "demo-user-2")
    document = upload(owner).json()
    assert other.get(f"/documents/{document['id']}").status_code == 404
    assert other.post(f"/documents/{document['id']}/share").status_code == 404
    assert owner.get("/documents/no-such-id").status_code == 404


def test_share_gives_a_link_that_downloads_without_a_session(app):
    owner = signed_in(app)
    document = upload(owner).json()
    link = share(owner, document["id"])
    assert link["url"].startswith("/d/") and link["expires_at"].endswith("Z")
    stranger = TestClient(app)
    answer = stranger.get(link["url"])
    assert answer.status_code == 200
    assert answer.content == PDF
    assert answer.headers["content-type"] == "application/pdf"
    assert "report.pdf" in answer.headers["content-disposition"]
    assert answer.headers["cache-control"] == "no-store, max-age=0"


def test_an_exhausted_link_is_410_and_identical_to_an_unknown_one(app):
    owner = signed_in(app)
    link = share(owner, upload(owner).json()["id"], max_downloads=1)
    stranger = TestClient(app)
    assert stranger.get(link["url"]).status_code == 200
    used_up = stranger.get(link["url"])
    unknown = stranger.get("/d/not-a-real-token")
    assert used_up.status_code == unknown.status_code == 410
    assert used_up.content == unknown.content
    assert used_up.headers["content-type"].startswith("text/html")
    assert b"no longer available" in used_up.content


def test_an_expired_or_revoked_link_is_410_with_the_same_body(app):
    owner = signed_in(app)
    document = upload(owner).json()
    expired = share(owner, document["id"])
    revoked = share(owner, document["id"])
    with session_scope(app.state.session_factory) as session:
        grants = session.query(DownloadGrant).order_by(DownloadGrant.created_at).all()
        grants[0].expires_at = utcnow() - timedelta(seconds=1)
        grants[1].revoked_at = utcnow()
    stranger = TestClient(app)
    first, second, unknown = stranger.get(expired["url"]), stranger.get(revoked["url"]), stranger.get("/d/zzz")
    assert first.status_code == second.status_code == 410
    assert first.content == second.content == unknown.content


def test_a_link_to_a_file_that_left_storage_is_410_and_keeps_its_download(app):
    owner = signed_in(app)
    document = upload(owner).json()
    link = share(owner, document["id"], max_downloads=1)
    app.state.storage.delete(f"documents/demo-user-1/{document['id']}")
    assert TestClient(app).get(link["url"]).status_code == 410
    with session_scope(app.state.session_factory) as session:
        assert session.query(DownloadGrant).one().download_count == 0


def test_share_limits_are_validated_and_only_a_hash_is_stored(app):
    owner = signed_in(app)
    document = upload(owner).json()
    bad = owner.post(f"/documents/{document['id']}/share", json={"ttl_seconds": 0})
    assert bad.status_code == 422
    token = share(owner, document["id"], ttl_seconds=60)["url"].removeprefix("/d/")
    with session_scope(app.state.session_factory) as session:
        grant = session.query(DownloadGrant).one()
        assert grant.token_hash != token and len(grant.token_hash) == 64
        assert grant.owner_id == document["id"]


def test_a_413_still_carries_the_cors_headers(app):
    who = signed_in(app)
    big = who.post("/documents", files={"file": ("big.bin", b"x" * (5 * 1024 * 1024 + 1), "application/octet-stream")},
                   headers={"Origin": "http://localhost:8078"})
    assert big.status_code == 413
    assert big.headers["access-control-allow-origin"] == "http://localhost:8078"
