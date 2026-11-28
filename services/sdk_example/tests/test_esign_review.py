"""E-signing review fixes: the job never overwrites a completed copy, loud failures, body caps, headers."""

import pytest
from bond_esign import EsignError
from esign_util import demo, kinds, post, tick, typed_form

from sdk_example.db import session_scope
from sdk_example.esign_wiring import TABLES, signed_key


def run_job(app, request_id):
    handler = app.state.job_registry.get("esign_complete")
    with session_scope(app.state.session_factory) as session:
        return handler(session, {"request_id": request_id}, app.state.clock.utcnow_naive())


def signed_request(client):
    created = demo(client)
    post(client, created, typed_form())
    return created


def test_a_completed_request_is_skipped_and_the_stored_copy_is_never_overwritten(client, app):
    created = signed_request(client)
    tick(client)
    rid = created["request_id"]
    with session_scope(app.state.session_factory) as session:
        wanted = session.get(TABLES.request, rid).signed_sha256
    app.state.settings = app.state.settings.__class__(**{**app.state.settings.__dict__, "tz": "Pacific/Auckland"})
    for _ in range(2):
        assert run_job(app, rid)["skipped"] is True
    import hashlib

    assert hashlib.sha256(app.state.storage.download_bytes(signed_key(rid))).hexdigest() == wanted
    assert kinds(client, created).count("completed") == 1


def test_a_failed_store_leaves_the_request_signed_for_the_retry(client, app, monkeypatch):
    created = signed_request(client)
    rid = created["request_id"]

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(app.state.storage, "upload_bytes", boom)
    with pytest.raises(OSError):
        run_job(app, rid)
    assert "completed" not in kinds(client, created)
    monkeypatch.undo()
    assert "summary" in run_job(app, rid)
    assert kinds(client, created).count("completed") == 1


def test_a_tampered_signer_row_makes_the_job_fail_loudly(client, app):
    created = signed_request(client)
    with session_scope(app.state.session_factory) as session:
        signer = session.query(TABLES.signer).filter_by(request_id=created["request_id"]).one()
        signer.typed_name = "Someone Else"
    with pytest.raises(EsignError) as caught:
        run_job(app, created["request_id"])
    assert caught.value.code in ("evidence_mismatch", "document_mismatch")


def test_a_corrupted_stored_signed_copy_is_a_404_and_not_a_download(client, app):
    created = signed_request(client)
    tick(client)
    url = created["sign_url"] + "/signed.pdf"
    assert client.get(url).status_code == 200
    before = kinds(client, created).count("downloaded")
    app.state.storage.upload_bytes(b"%PDF-1.4 not the signed copy", signed_key(created["request_id"]),
                                   content_type="application/pdf")
    assert client.get(url).status_code == 404
    assert kinds(client, created).count("downloaded") == before


def test_a_large_content_length_is_refused_before_reading(client):
    created = demo(client)
    reply = client.post(created["sign_url"], content=b"x=1",
                        headers={"content-type": "application/x-www-form-urlencoded", "content-length": "900000"})
    assert reply.status_code in (413, 400)  # the transport may also reject the short body; never a 500


def test_a_chunked_body_is_cut_off_at_the_cap(client):
    created = demo(client)

    def chunks():
        for _ in range(10):
            yield b"a" * 100_000

    reply = client.post(created["sign_url"], content=chunks(),
                        headers={"content-type": "application/x-www-form-urlencoded"})
    assert reply.status_code == 413


def test_the_sign_page_and_both_pdfs_are_never_cached_and_carry_the_csp(client):
    created = signed_request(client)
    tick(client)
    for path in ("", "/original.pdf", "/signed.pdf"):
        reply = client.get(created["sign_url"] + path)
        assert reply.status_code == 200, path
        assert reply.headers["cache-control"] == "no-store", path
        csp = reply.headers["content-security-policy"]
        assert "default-src 'self'" in csp and "script-src 'self'" in csp, path
