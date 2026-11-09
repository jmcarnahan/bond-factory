from datetime import datetime

import pytest
from conftest import Grant, load_document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bond_storage import LocalStorageService, StorageService, hash_token, make_download_router, mint, revoke
from bond_storage.router import GONE_BODY, NO_STORE

PDF = b"%PDF-1.4 test"


@pytest.fixture
def storage(tmp_path):
    s = LocalStorageService(tmp_path / "store")
    s.upload_bytes(PDF, "c/1/private/a.pdf")
    return s


def build(storage, factory, **kw):
    app = FastAPI()
    app.include_router(make_download_router(storage=storage, grant_model=Grant, document_loader=load_document,
                                            session_factory=factory, **kw))
    return TestClient(app)


def token(session, doc, **kw):
    grant, raw = mint(session, doc, grant_model=Grant, user_id="u", **kw)
    session.commit()
    return grant, raw


def test_success_inline_pdf_with_headers_and_count(storage, factory, session, doc):
    grant, raw = token(session, doc)
    r = build(storage, factory).get(f"/d/{raw}")
    assert r.status_code == 200 and r.content == PDF
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith('inline; filename="a.pdf"')
    for name, value in NO_STORE.items():
        assert r.headers[name] == value
    session.refresh(grant)
    assert grant.download_count == 1 and grant.last_ip == "testclient"


def test_attachment_for_other_types_and_attachment_kinds(storage, factory, session, doc):
    doc.content_type = "text/html"
    session.commit()
    _, raw = token(session, doc)
    assert build(storage, factory).get(f"/d/{raw}").headers["content-disposition"].startswith("attachment;")
    doc.content_type = "application/pdf"
    session.commit()
    _, raw2 = token(session, doc)
    assert build(storage, factory).get(f"/d/{raw2}").headers["content-disposition"].startswith("inline;")
    _, raw3 = token(session, doc)
    forced = build(storage, factory, attachment_kinds={"estimate"})
    assert forced.get(f"/d/{raw3}").headers["content-disposition"].startswith("attachment;")


def test_every_failure_is_the_same_410(storage, factory, session, doc):
    c = build(storage, factory)
    _, revoked = token(session, doc)
    _, expired = token(session, doc, now=lambda: datetime(2000, 1, 1))
    _, exhausted =token(session, doc, max_downloads=1)
    _, missing_file = token(session, doc)
    c.get(f"/d/{exhausted}")  # uses the one download
    with factory() as s:
        revoke(s.query(Grant).filter_by(token_hash=hash_token(revoked)).one())
        s.commit()
    storage.delete("c/1/private/a.pdf")
    answers = [c.get(f"/d/{t}") for t in (revoked, expired, exhausted, missing_file, "nope", "x" * 500, "%20")]
    for r in answers:
        assert r.status_code == 410
        assert r.content == GONE_BODY.encode()
        assert r.headers["content-type"] == "text/html; charset=utf-8"
        assert {k: r.headers[k] for k in NO_STORE} == NO_STORE
    assert len({(r.content, r.headers["content-type"], r.headers["content-length"]) for r in answers}) == 1
    assert "no longer available" in answers[0].text


def test_storage_error_is_503_text(factory, session, doc):
    class Broken(StorageService):
        def upload(self, local_path, key): ...
        def download(self, key, local_path): raise OSError("boom")
        def get_url(self, key, expires_in=3600, *, download_filename=None, content_type=None): return key
        def delete(self, key): ...
        def download_bytes(self, key): raise OSError("secret outage detail")

    _, raw = token(session, doc)
    r = build(Broken(), factory).get(f"/d/{raw}")
    assert r.status_code == 503 and r.headers["content-type"].startswith("text/plain")
    assert "secret" not in r.text and r.headers["cache-control"] == NO_STORE["Cache-Control"]


def test_transient_storage_fault_does_not_burn_a_single_use_link(factory, session, doc):
    class Flaky(StorageService):
        def __init__(self):
            self.calls = 0

        def upload(self, local_path, key): ...
        def download(self, key, local_path): ...
        def get_url(self, key, expires_in=3600, *, download_filename=None, content_type=None): return key
        def delete(self, key): ...

        def download_bytes(self, key):
            self.calls += 1
            if self.calls == 1:
                raise OSError("transient")
            return PDF

    grant, raw = token(session, doc, max_downloads=1)
    c = build(Flaky(), factory)
    assert c.get(f"/d/{raw}").status_code == 503
    session.refresh(grant)
    assert grant.download_count == 0
    assert c.get(f"/d/{raw}").status_code == 200
    assert c.get(f"/d/{raw}").status_code == 410


def test_wrong_bucket_is_503_not_the_410_page(monkeypatch, factory, session, doc):
    from botocore.stub import Stubber

    from bond_storage import S3StorageService, reset_clients

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    reset_clients()
    s3 = S3StorageService("gone-bucket", region="us-west-1")
    grant, raw = token(session, doc, max_downloads=1)
    with Stubber(s3.s3) as stub:
        stub.add_client_error("get_object", "NoSuchBucket", http_status_code=404)
        r = build(s3, factory).get(f"/d/{raw}")
    reset_clients()
    assert r.status_code == 503 and r.headers["content-type"].startswith("text/plain")
    session.refresh(grant)
    assert grant.download_count == 0


def test_missing_object_does_not_burn_a_download(storage, factory, session, doc):
    grant, raw = token(session, doc, max_downloads=1)
    storage.delete("c/1/private/a.pdf")
    c = build(storage, factory)
    assert c.get(f"/d/{raw}").status_code == 410
    session.refresh(grant)
    assert grant.download_count == 0
    storage.upload_bytes(PDF, "c/1/private/a.pdf")
    assert c.get(f"/d/{raw}").status_code == 200


def test_client_ip_is_the_last_forwarded_hop_not_a_client_controlled_prefix(storage, factory, session, doc):
    grant, raw = token(session, doc, max_downloads=None)
    c = build(storage, factory)
    c.get(f"/d/{raw}", headers={"X-Forwarded-For": "6.6.6.6, " + "a" * 300 + " , 203.0.113.9 "})
    session.refresh(grant)
    assert grant.last_ip == "203.0.113.9"
    c.get(f"/d/{raw}", headers={"X-Forwarded-For": "1.1.1.1," + "b" * 100})  # an oversized hop is cut to 45
    session.refresh(grant)
    assert grant.last_ip == "b" * 45
    c.get(f"/d/{raw}", headers={"X-Forwarded-For": "1.1.1.1,"})  # an empty last hop falls back to the peer
    session.refresh(grant)
    assert grant.last_ip == "testclient"


def test_rate_limit_key_ip_ignores_the_spoofed_prefix(storage, factory, session, doc):
    _, raw = token(session, doc, max_downloads=None)
    seen = []
    c = build(storage, factory, rate_limit=lambda key, ip: seen.append(ip) or True)
    c.get(f"/d/{raw}", headers={"X-Forwarded-For": "evil-1, 203.0.113.9"})
    c.get(f"/d/{raw}", headers={"X-Forwarded-For": "evil-2, 203.0.113.9"})
    assert seen == ["203.0.113.9", "203.0.113.9"]


def test_rate_limit_hook_gets_hashed_token_and_ip(storage, factory, session, doc):
    _, raw = token(session, doc)
    seen = []

    def limit(key, ip):
        seen.append((key, ip))
        return len(seen) <= 1

    c = build(storage, factory, rate_limit=limit)
    assert c.get(f"/d/{raw}").status_code == 200
    r = c.get(f"/d/{raw}")
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    assert seen[0][0] != raw and len(seen[0][0]) == 64 and seen[0][1] == "testclient"


def test_after_download_runs_before_commit(storage, factory, session, doc):
    _, raw = token(session, doc)
    calls = []
    build(storage, factory, after_download=lambda s, d: calls.append(d.id)).get(f"/d/{raw}")
    assert calls == ["d1"]
