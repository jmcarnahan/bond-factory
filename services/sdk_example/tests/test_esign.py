"""E-signing on the example: the demo request, the signing page, the job, the downloads, the evidence."""

from esign_util import (
    demo,
    drawn_form,
    evidence,
    has_form,
    kinds,
    pages,
    pdf_text,
    post,
    request_row,
    tick,
    typed_form,
)

from sdk_example.esign_wiring import TABLES


def test_typed_happy_path_end_to_end(client, app):
    created = demo(client)
    assert created["sign_url"].startswith("/esign/sign/")
    page = client.get(created["sign_url"])
    assert page.status_code == 200 and has_form(page.text) and "Sign and accept" in page.text
    assert page.headers["content-security-policy"] == (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'")
    assert "<meta name=\"viewport\"" in page.text and "<style" not in page.text and "<script>" not in page.text
    assert "View the document (PDF)" in page.text
    assert client.get(created["sign_url"] + "/original.pdf").content.startswith(b"%PDF")

    reply = post(client, created, typed_form())
    assert reply.status_code == 303 and reply.headers["location"] == created["sign_url"]
    waiting = client.get(created["sign_url"])
    assert not has_form(waiting.text) and "Your signed copy is being prepared." in waiting.text
    assert client.get(created["sign_url"] + "/signed.pdf").status_code == 404

    ran = tick(client)["ran"]
    assert [job["job_type"] for job in ran if job["job_type"] == "esign_complete"] == ["esign_complete"]
    done = client.get(created["sign_url"])
    assert "Download signed copy" in done.text and "signed.pdf" in done.text
    signed = client.get(created["sign_url"] + "/signed.pdf")
    assert signed.status_code == 200 and signed.headers["content-type"] == "application/pdf"
    assert pages(signed.content) == 2 + 1  # the original pages plus one certificate page (more if it overflows)
    text = pdf_text(signed.content)
    assert "Signature certificate" in text and "Pat Sample" in text

    data = evidence(client, created)
    assert data["chain"]["ok"] and data["check"]["ok"]
    assert [e["kind"] for e in data["events"]] == [
        "created", "token_issued", "viewed", "consent_given", "signed", "document_built", "completed", "downloaded"]
    assert data["request"]["status"] == "completed"
    assert data["request"]["signed_sha256"] == request_row(app, created).signed_sha256


def test_drawn_signature_path(client):
    created = demo(client)
    assert post(client, created, drawn_form()).status_code == 303
    tick(client)
    signed = client.get(created["sign_url"] + "/signed.pdf")
    assert signed.status_code == 200 and "Signature certificate" in pdf_text(signed.content)
    signer = evidence(client, created)["signers"][0]
    assert signer["signature_kind"] == "drawn" and signer["signature_png_base64"]


def test_a_replayed_post_writes_nothing(client):
    created = demo(client)
    post(client, created, typed_form())
    before = kinds(client, created)
    again = post(client, created, typed_form())
    assert again.status_code == 303 and again.headers["location"] == created["sign_url"]
    assert kinds(client, created) == before
    ran = tick(client)["ran"]
    assert len([job for job in ran if job["job_type"] == "esign_complete"]) == 1


def test_a_refused_post_redirects_with_the_code_and_writes_nothing(client):
    created = demo(client)
    before = kinds(client, created)
    reply = post(client, created, typed_form(consent_accepted=""))
    assert reply.status_code == 303 and reply.headers["location"] == created["sign_url"] + "?error=consent_required"
    page = client.get(reply.headers["location"])
    assert "Please tick the box to agree to sign electronically." in page.text and has_form(page.text)
    assert kinds(client, created) == before + ["viewed"]  # the refused post wrote nothing; the page view is the one new event


def test_the_error_query_is_never_echoed(client):
    created = demo(client)
    page = client.get(created["sign_url"] + "?error=<script>alert(1)</script>")
    assert "alert(1)" not in page.text
    page = client.get(created["sign_url"] + "?error=consent_stale")
    assert "The agreement text changed." in page.text


def test_an_unknown_token_is_a_plain_404_page(client):
    for path in ("", "/original.pdf", "/signed.pdf"):
        assert client.get("/esign/sign/not-a-token" + path).status_code == 404
    assert "was not found" in client.get("/esign/sign/not-a-token").text
    assert client.post("/esign/sign/not-a-token", data=typed_form()).status_code == 404


def test_an_expired_request_page_has_no_form(client):
    created = demo(client, expires_in_seconds=-60)
    page = client.get(created["sign_url"])
    assert page.status_code == 200 and not has_form(page.text) and "expired" in page.text
    reply = post(client, created, typed_form())
    assert reply.headers["location"].endswith("?error=expired")
    assert "expired" in kinds(client, created)


def test_a_voided_request_page_has_no_form(client):
    created = demo(client)
    assert client.post(f"/esign/demo/{created['request_id']}/void").json()["status"] == "voided"
    page = client.get(created["sign_url"])
    assert not has_form(page.text) and "This document is not ready to sign yet." in page.text
    assert post(client, created, typed_form()).headers["location"].endswith("?error=not_open")


def test_a_completed_request_cannot_be_voided(client, app):
    import pytest
    from bond_esign import EsignError, void

    from sdk_example.db import session_scope

    created = demo(client)
    post(client, created, typed_form())
    tick(client)
    assert client.post(f"/esign/demo/{created['request_id']}/void").status_code == 409
    with session_scope(app.state.session_factory) as session:
        row = session.get(TABLES.request, created["request_id"])
        with pytest.raises(EsignError) as caught:
            void(session, TABLES, row, reason="late", ctx=None, now=app.state.clock.utcnow_naive())
        assert caught.value.code == "already_completed"


def test_the_policy_knobs_reach_the_panel(client):
    page = client.get(demo(client, allow_drawn=False)["sign_url"]).text
    assert 'data-allow-drawn="0"' in page and 'data-allow-typed="1"' in page
