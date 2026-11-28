"""verify_evidence: rows that the certificate prints are cross-checked against the hashed events."""

import pytest
from conftest import PLACEMENT, T, at, new_request, sig_png, sign_it, signers_of
from sqlalchemy import text

from bond_esign import (
    EsignError,
    EvidenceCheck,
    SignerSpec,
    build_signed_pdf,
    complete,
    evidence,
    verify_evidence,
)


def scenario(session, pdf, *, completed=False):
    request = new_request(session, pdf, signers=[
        SignerSpec("Pat Example", email="pat@example.com", role="owner", key="k1", placement=PLACEMENT),
        SignerSpec("Sam Sample", placement=PLACEMENT)])  # fmt: skip
    pat, sam = signers_of(session, request)
    sign_it(session, pat, pdf, drawn_png=sig_png(), typed_name="Pat", now=at(1))
    sign_it(session, sam, pdf, typed_name="Sam Sample", now=at(2))
    if completed:
        complete(session, T, request, signed=build_signed_pdf(session, T, request, pdf=pdf), now=at(3))
    session.commit()
    return request, (pat, sam)


def tamper(session, table, column, value, row_id):
    session.execute(text(f"update {table} set {column}=:v where id=:i"), {"v": value, "i": row_id})
    session.commit()
    session.expire_all()


SIGNER_CASES = [
    ("name", "Someone Else", 0, "name differs"),
    ("email", "x@example.com", 0, "email differs"),
    ("role", "witness", 0, "role differs"),
    ("key", "k2", 0, "key differs"),
    ("typed_name", "Sam Forged", 1, "typed_name differs"),
    ("signed_at", "2026-01-01 00:00:00", 1, "signed_at differs"),
    ("signature_png", b"\x89PNG forged", 0, "signature"),
    ("signature_sha256", "e" * 64, 1, "signature_sha256 differs"),
    ("signature_kind", "drawn", 1, "signature_kind differs"),
    ("method", "in_person", 0, "method differs"),
]
REQUEST_CASES = [
    ("consent_text", "I agree to something else.", "consent_text"),
    ("title", "Forged title", "title differs"),
    ("consent_version", "consent/9", "consent_version differs"),
    ("consent_sha256", "a" * 64, "consent_sha256"),
    ("document_sha256", "b" * 64, "document_sha256 differs"),
]


def assert_flagged(session, request, pdf, needle):
    check = verify_evidence(session, T, request)
    assert isinstance(check, EvidenceCheck) and check.ok is False and check.chain.ok is True
    assert any(needle in p for p in check.problems), check.problems
    data = evidence(session, T, request)
    assert data["check"]["ok"] is False and data["check"]["problems"] == list(check.problems)
    assert data["chain"]["ok"] is True  # the event rows themselves were never touched
    with pytest.raises(EsignError) as info:
        build_signed_pdf(session, T, request, pdf=pdf)
    assert info.value.code == "evidence_mismatch" and info.value.message


def test_untampered_is_ok_before_and_after_completing(session, pdf_bytes):
    request, _ = scenario(session, pdf_bytes)
    check = verify_evidence(session, T, request)
    assert (check.ok, check.problems, check.chain.ok) == (True, (), True)
    assert evidence(session, T, request)["check"] == {"ok": True, "problems": []}
    complete(session, T, request, signed=build_signed_pdf(session, T, request, pdf=pdf_bytes), now=at(3))
    assert verify_evidence(session, T, request).ok
    assert build_signed_pdf(session, T, request, pdf=pdf_bytes)  # a rebuild after completing still passes


@pytest.mark.parametrize(("column", "value", "position", "needle"), SIGNER_CASES)
def test_a_tampered_signer_column_is_named(session, pdf_bytes, column, value, position, needle):
    request, signers = scenario(session, pdf_bytes)
    tamper(session, "esign_signers", column, value, signers[position].id)
    assert_flagged(session, request, pdf_bytes, needle)
    assert signers[position].id[:8] in " ".join(verify_evidence(session, T, request).problems)


@pytest.mark.parametrize(("column", "value", "needle"), REQUEST_CASES)
def test_a_tampered_request_column_is_named(session, pdf_bytes, column, value, needle):
    request, _ = scenario(session, pdf_bytes)
    tamper(session, "esign_requests", column, value, request.id)
    check = verify_evidence(session, T, request)
    assert check.ok is False and any(needle in p for p in check.problems), check.problems
    assert evidence(session, T, request)["check"]["ok"] is False
    if column != "document_sha256":  # a different document hash trips the evidence check first, too
        with pytest.raises(EsignError) as info:
            build_signed_pdf(session, T, request, pdf=pdf_bytes)
        assert info.value.code == "evidence_mismatch"


@pytest.mark.parametrize(("column", "value", "needle"), [("signed_sha256", "c" * 64, "signed_sha256"),
                                                          ("sealed", True, "sealed")])
def test_a_tampered_completed_request_is_named(session, pdf_bytes, column, value, needle):
    request, _ = scenario(session, pdf_bytes, completed=True)
    tamper(session, "esign_requests", column, value, request.id)
    assert_flagged(session, request, pdf_bytes, needle)


def test_a_signed_signer_without_a_signed_event_is_flagged(session, pdf_bytes):
    request, signers = scenario(session, pdf_bytes)
    tamper(session, "esign_signers", "status", "pending", signers[1].id)
    check = verify_evidence(session, T, request)
    assert not check.ok and any("has a signed event but is not signed" in p for p in check.problems)


def test_a_broken_chain_is_reported_in_the_problems(session, pdf_bytes):
    request, _ = scenario(session, pdf_bytes)
    session.execute(text("update esign_events set kind='voided' where seq=2"))
    session.commit()
    session.expire_all()
    check = verify_evidence(session, T, request)
    assert not check.ok and not check.chain.ok and check.chain.broken_seq == 2
