import pytest
from conftest import (
    CONSENT,
    CTX,
    NOW,
    PLACEMENT,
    T,
    at,
    blank_png,
    events_of,
    expect,
    kinds_of,
    new_request,
    sig_png,
    sign_it,
    signed_doc,
    signers_of,
)

from bond_esign import Policy, RequestContext, SignerSpec, decline, evidence, sha256_hex, void


def one(session, pdf, **kw):
    request = new_request(session, pdf, **kw)
    return request, signers_of(session, request)[0]


def test_typed_signature_records_everything_and_orders_the_events(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    out = sign_it(session, signer, pdf_bytes, typed_name="  Pat Example  ")
    assert out.replay is False and out.all_signed is True and out.request is request and out.signer is signer
    assert request.status == "signed"
    assert (signer.status, signer.method, signer.witness) == ("signed", "link", None)
    assert (signer.signature_kind, signer.typed_name, signer.signature_png) == ("typed", "Pat Example", None)
    assert signer.signature_sha256 == sha256_hex(b"Pat Example")
    assert (signer.signed_at, signer.ip, signer.user_agent) == (at(1), CTX.ip, CTX.user_agent)
    consent, signed = events_of(session, request)[-2:]
    assert (consent.kind, signed.kind) == ("consent_given", "signed")
    assert consent.data == {"version": "consent/1", "language": "en", "sha256": request.consent_sha256}
    assert signed.data == {
        "kind": "typed", "signature_sha256": signer.signature_sha256, "method": "link", "typed_name": "Pat Example",
        "name": "Pat Example",
    }
    for ev in (consent, signed):
        assert (ev.signer_id, ev.ip, ev.user_agent, ev.at) == (signer.id, CTX.ip, CTX.user_agent, at(1))


def test_drawn_signature_is_normalised_and_the_typed_name_is_kept_alongside(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes, drawn_png=sig_png(), typed_name="Pat E.")
    assert signer.signature_kind == "drawn" and signer.typed_name == "Pat E."
    assert signer.signature_png.startswith(b"\x89PNG") and signer.signature_sha256 == sha256_hex(signer.signature_png)
    assert events_of(session, request)[-1].data["kind"] == "drawn"


def test_drawn_without_a_typed_name_is_fine(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes, typed_name=None, drawn_png=sig_png())
    assert signer.typed_name is None and signer.signature_kind == "drawn"


def test_replay_writes_nothing_even_with_a_different_payload(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes)
    before = (len(events_of(session, request)), signer.signature_sha256, signer.signed_at, signer.typed_name)
    again = sign_it(session, signer, pdf_bytes, typed_name="Someone Else", drawn_png=sig_png(), now=at(30))
    assert again.replay is True and again.all_signed is True
    assert (len(events_of(session, request)), signer.signature_sha256, signer.signed_at, signer.typed_name) == before
    # a replay with garbage still writes nothing and does not raise
    assert sign_it(session, signer, b"junk", consent_accepted=False, typed_name=None).replay is True
    assert len(events_of(session, request)) == before[0]


def test_replay_still_answers_after_the_request_is_completed_or_expired(session, pdf_bytes):
    from bond_esign import complete

    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes)
    complete(session, T, request, signed=signed_doc(), now=at(5))
    n = len(events_of(session, request))
    assert sign_it(session, signer, pdf_bytes, now=at(99999)).replay is True
    assert len(events_of(session, request)) == n


def test_two_signers_the_request_stays_open_until_both_have_signed(session, pdf_bytes):
    request = new_request(session, pdf_bytes, signers=[
        SignerSpec("Pat", placement=PLACEMENT), SignerSpec("Sam", placement=PLACEMENT),
    ])  # fmt: skip
    pat, sam = signers_of(session, request)
    first = sign_it(session, pat, pdf_bytes)
    assert first.all_signed is False and request.status == "open"
    assert sign_it(session, pat, pdf_bytes).replay is True and request.status == "open"
    second = sign_it(session, sam, pdf_bytes, typed_name="Sam Sample")
    assert second.all_signed is True and request.status == "signed"


def test_document_mismatch(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    with expect("document_mismatch"):
        sign_it(session, signer, pdf_bytes + b"\n%changed")
    assert signer.status == "pending" and kinds_of(session, request) == ["created"]


def test_consent_required_and_stale(session, pdf_bytes):
    _request, signer = one(session, pdf_bytes)
    with expect("consent_required"):
        sign_it(session, signer, pdf_bytes, consent_accepted=False)
    with expect("consent_stale"):
        sign_it(session, signer, pdf_bytes, consent_version="consent/0")
    assert signer.status == "pending"


def test_signature_required_when_nothing_or_only_blanks_are_given(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    with expect("signature_required"):
        sign_it(session, signer, pdf_bytes, typed_name=None)
    with expect("signature_required"):
        sign_it(session, signer, pdf_bytes, typed_name="   ")


def test_typed_and_drawn_can_each_be_switched_off(session, pdf_bytes):
    _, signer = one(session, pdf_bytes, policy=Policy(allow_typed=False))
    with expect("typed_not_allowed"):
        sign_it(session, signer, pdf_bytes)
    assert sign_it(session, signer, pdf_bytes, drawn_png=sig_png(), typed_name=None).replay is False
    _, other = one(session, pdf_bytes, policy=Policy(allow_drawn=False))
    with expect("drawn_not_allowed"):
        sign_it(session, other, pdf_bytes, drawn_png=sig_png())


def test_signature_invalid_for_bad_png_and_overlong_typed_name(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    with expect("signature_invalid"):
        sign_it(session, signer, pdf_bytes, drawn_png=b"not a png", typed_name=None)
    with expect("signature_invalid"):
        sign_it(session, signer, pdf_bytes, typed_name="x" * 121)
    with expect("signature_invalid"):  # a PNG header and nothing else
        sign_it(session, signer, pdf_bytes, drawn_png=b"\x89PNG\r\n\x1a\n", typed_name=None)
    with expect("signature_invalid"):  # a real PNG with no ink
        sign_it(session, signer, pdf_bytes, drawn_png=blank_png(), typed_name=None)


@pytest.mark.parametrize("name", ["李小龍", "Pat\nExample", "Pat \u200b", "Zoë 😀"])
def test_a_name_the_standard_fonts_cannot_draw_is_refused(session, pdf_bytes, name):
    _, signer = one(session, pdf_bytes)
    with expect("name_not_renderable"):
        sign_it(session, signer, pdf_bytes, typed_name=name)


def test_latin1_names_pass_and_the_any_charset_allows_wider_names(session, pdf_bytes):
    _, latin = one(session, pdf_bytes)
    sign_it(session, latin, pdf_bytes, typed_name="José Núñez-Ångström")
    assert latin.typed_name == "José Núñez-Ångström"
    _, wide = one(session, pdf_bytes, policy=Policy(typed_charset="any"))
    sign_it(session, wide, pdf_bytes, typed_name="李小龍")
    assert wide.typed_name == "李小龍"


def test_a_declined_voided_or_signed_request_is_not_open(session, pdf_bytes):
    _request, signer = one(session, pdf_bytes)
    decline(session, T, signer, reason=None, ctx=CTX, now=at(1))
    with expect("not_open"):
        sign_it(session, signer, pdf_bytes)
    request2, signer2 = one(session, pdf_bytes)
    void(session, T, request2, reason="mistake", ctx=CTX, now=at(1))
    with expect("not_open"):
        sign_it(session, signer2, pdf_bytes)


def test_an_expired_request_flips_with_an_event_then_refuses(session, pdf_bytes):
    from datetime import timedelta

    request, signer = one(session, pdf_bytes, expires_at=NOW + timedelta(hours=1))
    with expect("expired"):
        sign_it(session, signer, pdf_bytes, now=at(61))
    assert request.status == "expired" and kinds_of(session, request) == ["created", "expired"]
    with expect("expired"):  # already flipped: still "expired", no second event
        sign_it(session, signer, pdf_bytes, now=at(62))
    assert kinds_of(session, request) == ["created", "expired"]


def test_not_expired_just_before_the_deadline(session, pdf_bytes):
    from datetime import timedelta

    _, signer = one(session, pdf_bytes, expires_at=NOW + timedelta(hours=1))
    assert sign_it(session, signer, pdf_bytes, now=at(59, 59)).replay is False


def test_the_checks_run_in_the_documented_order(session, pdf_bytes):
    _, signer = one(session, pdf_bytes, policy=Policy(require_email_code=True))
    with expect("document_mismatch"):  # before consent, code and signature
        sign_it(session, signer, b"other", consent_accepted=False, typed_name=None)
    with expect("consent_required"):  # before the code
        sign_it(session, signer, pdf_bytes, consent_accepted=False, typed_name=None)
    with expect("consent_stale"):
        sign_it(session, signer, pdf_bytes, consent_version="old", typed_name=None)
    with expect("code_required"):  # before the signature is looked at
        sign_it(session, signer, pdf_bytes, typed_name=None)


def test_unknown_method_is_a_value_error(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    with pytest.raises(ValueError):
        sign_it(session, signer, pdf_bytes, method="carrier_pigeon")


def test_in_person_needs_an_actor_and_records_the_witness(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    with expect("in_person_needs_actor"):
        sign_it(session, signer, pdf_bytes, method="in_person")
    with expect("in_person_needs_actor"):
        sign_it(session, signer, pdf_bytes, method="in_person", ctx=RequestContext(ip="198.51.100.1"))
    sign_it(session, signer, pdf_bytes, method="in_person", ctx=RequestContext(ip="198.51.100.1", actor="staff-7"))
    assert (signer.method, signer.witness) == ("in_person", "staff-7")
    assert events_of(session, request)[-1].actor == "staff-7"
    assert events_of(session, request)[-1].data["method"] == "in_person"


def test_email_code_policy_needs_a_verified_code_and_records_email_code(session, pdf_bytes):
    from bond_esign import issue_code, verify_code

    request, signer = one(session, pdf_bytes, policy=Policy(require_email_code=True))
    with expect("code_required"):
        sign_it(session, signer, pdf_bytes)
    code = issue_code(session, T, signer, now=at(0, 30))
    assert verify_code(session, T, signer, code, ctx=CTX, now=at(1)) is True
    sign_it(session, signer, pdf_bytes)
    assert signer.method == "email_code" and events_of(session, request)[-1].data["method"] == "email_code"


def test_in_person_skips_the_code_even_when_the_policy_asks_for_one(session, pdf_bytes):
    _, signer = one(session, pdf_bytes, policy=Policy(require_email_code=True))
    sign_it(session, signer, pdf_bytes, method="in_person", ctx=RequestContext(actor="staff-1"))
    assert signer.method == "in_person"


def test_asking_for_method_email_code_without_a_code_is_refused(session, pdf_bytes):
    _, signer = one(session, pdf_bytes)
    with expect("code_required"):
        sign_it(session, signer, pdf_bytes, method="email_code")


def test_signing_leaves_the_chain_intact_and_evidence_matches(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes)
    data = evidence(session, T, request)
    assert data["chain"]["ok"] is True and data["chain"]["count"] == 3
    assert CONSENT.text == data["request"]["consent_text"]
