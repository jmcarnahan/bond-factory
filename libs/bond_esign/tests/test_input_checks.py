"""Inputs are validated before state changes; programming errors are ValueError, signer errors EsignError."""

import io
import os
import subprocess
import sys
from datetime import timedelta

import pytest
from conftest import (
    CONSENT,
    CTX,
    NOW,
    T,
    at,
    events_of,
    expect,
    make_pdf,
    new_request,
    sign_it,
    signed_doc,
    signers_of,
)
from reportlab.pdfgen import canvas

from bond_esign import (
    Consent,
    Policy,
    RequestContext,
    SignedDocument,
    SignerSpec,
    complete,
    create_request,
    decline,
    find_signer_by_token,
    issue_token,
    page_count,
    sha256_hex,
    signing_view,
    verify_chain,
    void,
)
from bond_esign._rows import clean


def test_complete_refuses_a_signed_document_whose_hash_or_pages_do_not_match_its_bytes(session, pdf_bytes):
    request = new_request(session, pdf_bytes)
    sign_it(session, signers_of(session, request)[0], pdf_bytes)
    good = signed_doc()
    with pytest.raises(ValueError, match="sha256"):
        complete(session, T, request, signed=SignedDocument(pdf=good.pdf, sha256="a" * 64, pages=3), now=at(3))
    with pytest.raises(ValueError, match="pages"):
        complete(session, T, request, signed=SignedDocument(pdf=good.pdf, sha256=good.sha256, pages=9), now=at(3))
    junk = b"not a pdf"
    with pytest.raises(ValueError, match="readable"):
        complete(session, T, request, signed=SignedDocument(pdf=junk, sha256=sha256_hex(junk), pages=1), now=at(3))
    assert request.status == "signed"
    assert complete(session, T, request, signed=good, now=at(3)).status == "completed"


BAD_POLICIES = [
    ({"allow_typed": False, "allow_drawn": False}, "allow_typed"),
    ({"max_signers": 0}, "max_signers"), ({"max_signature_bytes": -1}, "max_signature_bytes"),
    ({"max_pdf_bytes": 0}, "max_pdf_bytes"), ({"code_ttl_seconds": 0}, "code_ttl_seconds"),
    ({"code_max_attempts": 0}, "code_max_attempts"), ({"code_resend_seconds": -1}, "code_resend_seconds"),
    ({"view_event_gap_seconds": -5}, "view_event_gap_seconds"), ({"typed_charset": "utf-8"}, "typed_charset"),
]  # fmt: skip


@pytest.mark.parametrize(("kw", "needle"), BAD_POLICIES)
def test_a_bad_policy_is_a_value_error(session, pdf_bytes, kw, needle):
    with pytest.raises(ValueError, match=needle):
        new_request(session, pdf_bytes, policy=Policy(**kw))


def test_zero_resend_and_view_gap_are_allowed(session, pdf_bytes):
    assert new_request(session, pdf_bytes, policy=Policy(code_resend_seconds=0, view_event_gap_seconds=0))


BAD_ARGS = [
    ({"consent": Consent("", "en", "text")}, "consent"), ({"consent": Consent("v1", "en", "   ")}, "consent"),
    ({"consent": Consent("v1", "en", "")}, "consent"), ({"title": ""}, "title"), ({"title": " \x00 "}, "title"),
    ({"signers": [SignerSpec(name="  ")]}, "blank name"), ({"signers": [SignerSpec(name="")]}, "blank name"),
    ({"expires_at": NOW}, "expires_at"), ({"expires_at": NOW - timedelta(days=1)}, "expires_at"),
]  # fmt: skip


@pytest.mark.parametrize(("kw", "needle"), BAD_ARGS)
def test_blank_or_past_values_are_a_value_error_and_write_nothing(session, pdf_bytes, kw, needle):
    from sqlalchemy import func, select

    with pytest.raises(ValueError, match=needle):
        new_request(session, pdf_bytes, **kw)
    assert session.execute(select(func.count()).select_from(T.request)).scalar() == 0


def test_a_future_expiry_is_fine(session, pdf_bytes):
    assert new_request(session, pdf_bytes, expires_at=NOW + timedelta(seconds=1))


# ---- surrogates and state -----------------------------------------------------------------------------

SURR = RequestContext(ip="1.2.3.\ud800", user_agent="UA\udfff/1", actor="staff\ud83d")


def test_clean_replaces_lone_surrogates():
    out = clean("a\ud800b", 10)
    assert out == "a?b" and out.encode("utf-8")


def test_surrogates_in_context_reasons_and_names_never_reach_the_database_layer(session, pdf_bytes):
    request, other = new_request(session, pdf_bytes), new_request(session, pdf_bytes)
    signer, other_signer = signers_of(session, request)[0], signers_of(session, other)[0]
    sign_it(session, signer, pdf_bytes, ctx=SURR, typed_name="Pat\ud800 Example")
    assert signer.typed_name == "Pat? Example" and signer.user_agent == "UA?/1"
    decline(session, T, other_signer, reason="no\ud800", ctx=SURR, now=at(2))
    third = new_request(session, pdf_bytes, title="T\ud800", signers=[SignerSpec(name="N\udc80")])
    void(session, T, third, reason="x\ud800", ctx=SURR, now=at(2))
    assert (other_signer.decline_reason, third.void_reason, third.title) == ("no?", "x?", "T?")
    signing_view(session, T, signers_of(session, third)[0], ctx=SURR, now=at(5))
    session.commit()
    for r in (request, other, third):
        assert verify_chain(session, T, r).ok
        for e in events_of(session, r):
            f"{e.ip}{e.user_agent}{e.actor}{e.data}".encode()


def test_a_refused_call_leaves_the_state_unchanged(session, pdf_bytes):
    request = new_request(session, pdf_bytes, expires_at=NOW + timedelta(days=1))
    signer = signers_of(session, request)[0]
    before = len(events_of(session, request))
    with expect("signature_required"):
        sign_it(session, signer, pdf_bytes, ctx=SURR, typed_name="\x00\ud800"[:1])
    with expect("signature_invalid"):
        sign_it(session, signer, pdf_bytes, ctx=SURR, typed_name="x" * 500)
    assert (signer.status, request.status, signer.signed_at, signer.ip) == ("pending", "open", None, None)
    assert len(events_of(session, request)) == before


def test_a_surrogate_token_finds_nobody_and_a_real_token_still_works(session, pdf_bytes):
    request = new_request(session, pdf_bytes)
    signer = signers_of(session, request)[0]
    token = issue_token(session, T, signer, now=at(0))
    assert find_signer_by_token(session, T, "\ud800" + token, now=at(1)) is None
    assert find_signer_by_token(session, T, "\ud800", now=at(1)) is None
    assert find_signer_by_token(session, T, token, now=at(1)) is signer


def test_decline_by_a_signer_who_has_signed_while_the_request_is_open_is_not_open(session, pdf_bytes):
    request = new_request(session, pdf_bytes, signers=[SignerSpec("Pat Example"), SignerSpec("Sam Sample")])
    pat, _ = signers_of(session, request)
    sign_it(session, pat, pdf_bytes)
    assert request.status == "open"
    before = len(events_of(session, request))
    with expect("not_open"):
        decline(session, T, pat, reason="changed my mind", ctx=CTX, now=at(3))
    assert (pat.status, request.status, pat.decline_reason) == ("signed", "open", None)
    assert len(events_of(session, request)) == before


# ---- encrypted PDFs, the certs CLI ---------------------------------------------------------------------


def test_an_encrypted_pdf_is_refused(session):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt="owner-secret")
    c.drawString(72, 700, "Synthetic secret estimate")
    c.showPage()
    c.save()
    secret = buf.getvalue()
    assert b"/Encrypt" in secret
    with expect("invalid_pdf"):
        page_count(secret)
    with expect("invalid_pdf"):
        create_request(session, T, pdf=secret, title="T", consent=CONSENT, now=NOW, signers=[SignerSpec("Pat")])
    assert page_count(make_pdf(1)) == 1


def test_the_certs_cli_sets_mode_0600_on_an_existing_file(tmp_path):
    pytest.importorskip("cryptography")
    out = tmp_path / "seal.p12"
    out.write_bytes(b"old")
    os.chmod(out, 0o644)
    subprocess.run(
        [sys.executable, "-m", "bond_esign.certs", "--cn", "Sample Sealer", "--org", "Sample Org", "--out", str(out),
         "--passphrase", "pw"],
        capture_output=True, text=True, check=True, cwd=tmp_path,
    )  # fmt: skip
    assert (out.stat().st_mode & 0o777) == 0o600 and out.read_bytes() != b"old"
