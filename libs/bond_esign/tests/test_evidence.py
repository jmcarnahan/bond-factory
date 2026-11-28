import base64
import json

from conftest import CTX, T, at, new_request, sig_png, sign_it, signed_doc, signers_of

from bond_esign import SignerSpec, complete, evidence, issue_code, issue_token, verify_chain

REQUEST_KEYS = {
    "id", "status", "title", "subject_type", "subject_id", "document_sha256", "document_bytes", "page_count",
    "consent_version", "consent_language", "consent_sha256", "consent_text", "policy", "expires_at",
    "signed_sha256", "sealed", "timestamped", "completed_at", "voided_at", "declined_at", "void_reason",
    "created_at", "updated_at", "company_id",
}  # fmt: skip
SIGNER_KEYS = {
    "id", "request_id", "position", "name", "email", "role", "key", "status", "placement", "date_placement",
    "token_expires_at", "code_expires_at", "code_sent_at", "code_verified_at", "code_attempts", "method",
    "witness", "signature_kind", "typed_name", "signature_sha256", "signed_at", "ip", "user_agent",
    "decline_reason", "created_at", "updated_at", "signature_png_base64",
}  # fmt: skip


def build(session, pdf):
    request = new_request(session, pdf, meta={"app": "private"}, company_id="co-1", subject_type="estimate",
                          subject_id="E-1", signers=[SignerSpec("Pat Example", "pat@example.com"),
                                                     SignerSpec("Sam Sample")])  # fmt: skip
    pat, sam = signers_of(session, request)
    token = issue_token(session, T, pat, now=at(0))
    code = issue_code(session, T, pat, now=at(0))
    sign_it(session, pat, pdf, drawn_png=sig_png(), typed_name="Pat", now=at(1))
    sign_it(session, sam, pdf, typed_name="Sam Sample", now=at(2))
    complete(session, T, request, signed=signed_doc("d"), now=at(3))
    return request, pat, sam, token, code


def test_shape_columns_and_chain(session, pdf_bytes):
    request, *_ = build(session, pdf_bytes)
    data = evidence(session, T, request)
    assert data["schema"] == "bond.esign_evidence/0.1" and set(data) == {"schema", "request", "signers", "events", "chain", "check"}
    assert set(data["request"]) == REQUEST_KEYS
    assert [set(s) for s in data["signers"]] == [SIGNER_KEYS, SIGNER_KEYS]
    assert data["request"]["status"] == "completed" and data["request"]["signed_sha256"] == request.signed_sha256
    assert data["request"]["company_id"] == "co-1" and data["request"]["policy"]["max_signers"] == 10
    events = data["events"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert [e["kind"] for e in events] == [
        "created", "token_issued", "code_sent", "consent_given", "signed", "consent_given", "signed",
        "document_built", "completed",
    ]  # fmt: skip
    assert events[0]["prev_hash"] == "0" * 64 and events[1]["prev_hash"] == events[0]["row_hash"]
    check = verify_chain(session, T, request)
    assert data["chain"] == {"ok": True, "count": len(events), "head": events[-1]["row_hash"]} and check.ok


def test_datetimes_are_iso_seconds_with_z_and_none_stays_null(session, pdf_bytes):
    request, *_ = build(session, pdf_bytes)
    data = evidence(session, T, request)
    assert data["request"]["completed_at"] == "2026-11-08T10:03:00Z" and data["request"]["voided_at"] is None
    assert data["request"]["created_at"] == "2026-11-08T10:00:00Z"
    assert data["signers"][0]["signed_at"] == "2026-11-08T10:01:00Z"
    assert data["events"][0]["at"] == "2026-11-08T10:00:00Z"
    assert data["signers"][1]["email"] is None and data["signers"][1]["placement"] is None


def test_credentials_and_app_meta_are_never_exported(session, pdf_bytes):
    request, pat, _, token, code = build(session, pdf_bytes)
    blob = json.dumps(evidence(session, T, request))  # also proves it is JSON-serialisable
    for secret in (token, code, pat.token_sha256, "private"):
        assert secret not in blob
    assert "token_sha256" not in blob and "code_sha256" not in blob and '"meta"' not in blob


def test_signature_image_is_base64_and_typed_signers_have_none(session, pdf_bytes):
    request, pat, *_ = build(session, pdf_bytes)
    first, second = evidence(session, T, request)["signers"]
    assert base64.b64decode(first["signature_png_base64"]) == pat.signature_png
    assert "signature_png" not in first and second["signature_png_base64"] is None
    assert (first["signature_kind"], second["signature_kind"]) == ("drawn", "typed")
    assert first["signature_sha256"] == pat.signature_sha256


def test_events_carry_ip_agent_actor_and_data_and_a_broken_chain_is_reported(session, pdf_bytes):
    from sqlalchemy import text

    request, *_ = build(session, pdf_bytes)
    signed = next(e for e in evidence(session, T, request)["events"] if e["kind"] == "signed")
    assert (signed["ip"], signed["user_agent"], signed["data"]["kind"]) == (CTX.ip, CTX.user_agent, "drawn")
    session.execute(text("update esign_events set data='{\"x\": 1}' where seq=4"))
    session.expire_all()
    data = evidence(session, T, request)
    assert data["chain"]["ok"] is False and data["chain"]["count"] == len(data["events"])
