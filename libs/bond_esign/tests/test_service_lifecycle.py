from datetime import timedelta

import pytest
from conftest import (
    CTX,
    NOW,
    PLACEMENT,
    T,
    at,
    events_of,
    expect,
    kinds_of,
    new_request,
    sig_png,
    sign_it,
    signed_doc,
    signers_of,
)

from bond_esign import (
    Brand,
    CertificateLabels,
    Policy,
    RequestContext,
    SignedDocument,
    SignerSpec,
    build,
    build_signed_pdf,
    complete,
    decline,
    expire_due,
    record_delivery,
    record_download,
    sha256_hex,
    signing_view,
    void,
)


def one(session, pdf, **kw):
    request = new_request(session, pdf, **kw)
    return request, signers_of(session, request)[0]


def signed_request(session, pdf, **kw):
    request, signer = one(session, pdf, **kw)
    sign_it(session, signer, pdf)
    return request, signer


def doc(tag="a", **kw):
    return signed_doc(tag, **kw)


# ---- decline, void, expire ------------------------------------------------------------------------------

def test_decline_marks_signer_and_request(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    assert decline(session, T, signer, reason="too dear", ctx=CTX, now=at(2)) is request
    assert (signer.status, signer.decline_reason, request.status, request.declined_at) == (
        "declined", "too dear", "declined", at(2))  # fmt: skip
    last = events_of(session, request)[-1]
    assert (last.kind, last.signer_id, last.data, last.ip) == ("declined", signer.id, {"reason": "too dear"}, CTX.ip)
    with expect("not_open"):
        decline(session, T, signer, reason=None, ctx=CTX, now=at(3))


def test_decline_after_signing_or_expiry_is_refused(session, pdf_bytes):
    _, signer = signed_request(session, pdf_bytes)
    with expect("not_open"):
        decline(session, T, signer, reason=None, ctx=CTX, now=at(3))
    _request, other = one(session, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    with expect("expired"):
        decline(session, T, other, reason=None, ctx=CTX, now=at(6))


def test_void_open_declined_and_expired_requests(session, pdf_bytes):
    for prepare in ("open", "declined", "expired"):
        request, signer = one(session, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
        if prepare == "declined":
            decline(session, T, signer, reason=None, ctx=CTX, now=at(1))
        elif prepare == "expired":
            assert expire_due(session, T, now=at(10)) >= 1
        void(session, T, request, reason="entered in error", ctx=CTX, now=at(11))
        assert (request.status, request.void_reason, request.voided_at) == ("voided", "entered in error", at(11))
        assert events_of(session, request)[-1].data == {"reason": "entered in error"}


def test_void_twice_changes_nothing_and_writes_no_event(session, pdf_bytes):
    request, _ = one(session, pdf_bytes)
    void(session, T, request, reason="first", ctx=CTX, now=at(1))
    n = len(events_of(session, request))
    assert void(session, T, request, reason="second", ctx=CTX, now=at(9)) is request
    assert (request.void_reason, request.voided_at, len(events_of(session, request))) == ("first", at(1), n)


def test_void_after_every_signer_signed_is_refused_and_writes_nothing(session, pdf_bytes):
    request, _ = signed_request(session, pdf_bytes)
    n = len(events_of(session, request))
    with expect("already_completed"):
        void(session, T, request, reason="too late", ctx=CTX, now=at(4))
    assert (request.status, request.voided_at, len(events_of(session, request))) == ("signed", None, n)


def test_void_with_one_of_two_signers_signed_still_works(session, pdf_bytes):
    request = new_request(session, pdf_bytes, signers=[SignerSpec("Pat Example", placement=PLACEMENT), SignerSpec("Sam")])
    sign_it(session, signers_of(session, request)[0], pdf_bytes)
    assert request.status == "open"
    void(session, T, request, reason="changed my mind", ctx=CTX, now=at(4))
    assert request.status == "voided"


def test_void_after_completion_is_refused(session, pdf_bytes):
    request, _ = signed_request(session, pdf_bytes)
    complete(session, T, request, signed=doc(), now=at(3))
    with expect("already_completed"):
        void(session, T, request, reason="too late", ctx=CTX, now=at(4))
    assert request.status == "completed"


def test_expire_due_flips_only_open_overdue_requests(session, pdf_bytes):
    due, _ = one(session, pdf_bytes, expires_at=NOW + timedelta(hours=1))
    later, _ = one(session, pdf_bytes, expires_at=NOW + timedelta(days=1))
    never, _ = one(session, pdf_bytes)
    done, signer = one(session, pdf_bytes, expires_at=NOW + timedelta(hours=1))
    sign_it(session, signer, pdf_bytes)
    assert expire_due(session, T, now=at(60)) == 1  # only `due`; the boundary is inclusive; signed is not open
    assert (due.status, later.status, never.status, done.status) == ("expired", "open", "open", "signed")
    assert kinds_of(session, due) == ["created", "expired"] and events_of(session, due)[-1].ip is None
    assert expire_due(session, T, now=at(61)) == 0


# ---- signing_view ---------------------------------------------------------------------------------------

def test_signing_view_reports_what_the_page_needs(session, pdf_bytes):
    _request, signer = one(session, pdf_bytes, policy=Policy(allow_drawn=False, require_email_code=True))
    view = signing_view(session, T, signer, ctx=CTX, now=at(1))
    assert (view.request_status, view.signer_status, view.can_sign, view.reason) == ("open", "pending", True, None)
    assert (view.needs_code, view.code_verified, view.allow_typed, view.allow_drawn) == (True, False, True, False)
    assert (view.signer_name, view.title, view.consent.version, view.consent.text.startswith("I agree")) == (
        "Pat Example", "Estimate 100", "consent/1", True)  # fmt: skip


def test_viewed_is_recorded_at_most_once_per_gap(session, pdf_bytes):
    request, signer = one(session, pdf_bytes, policy=Policy(view_event_gap_seconds=600))
    for minute in (1, 2, 9):
        signing_view(session, T, signer, ctx=CTX, now=at(minute))
    assert kinds_of(session, request).count("viewed") == 1  # 1 -> recorded; 2, 9 inside the gap of 10 min
    signing_view(session, T, signer, ctx=CTX, now=at(11))
    assert kinds_of(session, request).count("viewed") == 2
    assert events_of(session, request)[-1].signer_id == signer.id and events_of(session, request)[-1].ip == CTX.ip


def test_signing_view_reasons_for_closed_requests(session, pdf_bytes):
    req, signer = one(session, pdf_bytes, expires_at=NOW + timedelta(minutes=5))
    view = signing_view(session, T, signer, ctx=CTX, now=at(6))
    assert (view.can_sign, view.reason, view.request_status) == (False, "expired", "expired")
    assert kinds_of(session, req) == ["created", "expired"]  # flipped, not raised, and not "viewed"
    req2, signer2 = one(session, pdf_bytes)
    void(session, T, req2, reason="x", ctx=CTX, now=at(1))
    assert signing_view(session, T, signer2, ctx=CTX, now=at(2)).reason == "not_open"
    req3, signer3 = signed_request(session, pdf_bytes)
    view3 = signing_view(session, T, signer3, ctx=CTX, now=at(2))
    assert (view3.can_sign, view3.reason, view3.signer_status) == (False, "not_open", "signed")
    assert "viewed" not in kinds_of(session, req3)


# ---- build_signed_pdf and complete ----------------------------------------------------------------------

@pytest.fixture
def fake_compose(monkeypatch):
    seen = {}

    def compose(pdf, *, title, stamps, certificate, labels, brand=None, sealer=None):
        seen.update(pdf=pdf, title=title, stamps=list(stamps), certificate=certificate, labels=labels,
                    brand=brand, sealer=sealer)  # fmt: skip
        return SignedDocument(pdf=b"%PDF-fake", sha256=sha256_hex(b"%PDF-fake"), pages=3)

    monkeypatch.setattr(build, "compose", compose)
    return seen


def test_build_needs_a_signed_request_and_the_original_bytes(session, pdf_bytes, fake_compose):
    request, _ = one(session, pdf_bytes)
    with expect("not_ready"):
        build_signed_pdf(session, T, request, pdf=pdf_bytes)
    request2, _signer = signed_request(session, pdf_bytes)
    with expect("document_mismatch"):
        build_signed_pdf(session, T, request2, pdf=pdf_bytes + b" ")
    assert fake_compose == {}


def test_build_gathers_stamps_and_certificate_data_and_writes_nothing(session, pdf_bytes, fake_compose):
    request = new_request(session, pdf_bytes, signers=[
        SignerSpec("Pat Example", "pat@example.com", placement=PLACEMENT, date_placement=PLACEMENT),
        SignerSpec("Sam Sample"),  # no placement: certificate only
    ])  # fmt: skip
    pat, sam = signers_of(session, request)
    sign_it(session, pat, pdf_bytes, drawn_png=sig_png(), typed_name="Pat", now=at(1))
    sign_it(session, sam, pdf_bytes, typed_name="Sam Sample", now=at(2))
    session.expire_all()
    rows_before = len(events_of(session, request))
    brand = Brand(name="Example Roofing")
    out = build_signed_pdf(session, T, request, pdf=pdf_bytes, brand=brand, zone="America/Chicago")
    assert out.pdf == b"%PDF-fake" and fake_compose["pdf"] == pdf_bytes and fake_compose["brand"] is brand
    assert fake_compose["title"] == "Estimate 100" and fake_compose["sealer"] is None
    assert isinstance(fake_compose["labels"], CertificateLabels)
    (stamp,) = fake_compose["stamps"]  # Sam has no box
    assert stamp.png == pat.signature_png and stamp.typed_name is None
    assert stamp.placement.page == 2 and stamp.date_placement == stamp.placement
    assert stamp.caption == f"Signed electronically by Pat Example, Nov 8, 2026, ref {pat.id[:8]}"
    assert stamp.date_text == "Nov 8, 2026"
    cert = fake_compose["certificate"]
    assert (cert.request_id, cert.title, cert.zone, cert.page_count) == (request.id, "Estimate 100", "America/Chicago", 2)
    assert [s.name for s in cert.signers] == ["Pat Example", "Sam Sample"]  # position order
    assert cert.signers[0].ref == pat.id[:8] and cert.signers[0].signature_png == pat.signature_png
    assert cert.signers[1].typed_name == "Sam Sample" and cert.signers[1].signature_kind == "typed"
    rows = events_of(session, request)
    assert [e.seq for e in cert.events] == list(range(1, len(rows) + 1))
    assert cert.events[-1].signer_name == "Sam Sample" and cert.events[0].signer_name is None
    assert cert.chain_head == rows[-1].row_hash and len(rows) == rows_before  # no event written
    assert request.status == "signed" and request.signed_sha256 is None


def test_a_typed_stamp_uses_the_typed_name_and_local_date_crosses_midnight(session, pdf_bytes, fake_compose):
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes, now=NOW + timedelta(hours=12))  # 22:00 UTC on Nov 8
    build_signed_pdf(session, T, request, pdf=pdf_bytes, zone="Pacific/Auckland")
    (stamp,) = fake_compose["stamps"]
    assert stamp.typed_name == "Pat Example" and stamp.png is None and stamp.date_text is None
    assert "Nov 9, 2026" in stamp.caption  # 22:00 UTC on the 8th is already the 9th in Auckland


def test_build_accepts_a_completed_request_and_rejects_an_unknown_zone(session, pdf_bytes, fake_compose):
    request, _ = signed_request(session, pdf_bytes)
    with pytest.raises(ValueError):
        build_signed_pdf(session, T, request, pdf=pdf_bytes, zone="Nowhere/Land")
    complete(session, T, request, signed=doc(), now=at(3))
    build_signed_pdf(session, T, request, pdf=pdf_bytes)
    assert "stamps" in fake_compose


def test_build_passes_the_sealer_through(session, pdf_bytes, fake_compose):
    request, _ = signed_request(session, pdf_bytes)
    sealer = object()
    build_signed_pdf(session, T, request, pdf=pdf_bytes, sealer=sealer)
    assert fake_compose["sealer"] is sealer


def test_complete_records_the_build_and_is_idempotent(session, pdf_bytes):
    request, _ = signed_request(session, pdf_bytes)
    built = doc("b", sealed=True, timestamped=True, timestamp_url="https://tsa.example.com")
    complete(session, T, request, signed=built, now=at(3))
    assert (request.status, request.signed_sha256, request.sealed, request.timestamped, request.completed_at) == (
        "completed", built.sha256, True, True, at(3))  # fmt: skip
    built_ev, done_ev = events_of(session, request)[-2:]
    assert (built_ev.kind, done_ev.kind) == ("document_built", "completed")
    assert built_ev.data == {"sha256": built.sha256, "pages": 3, "sealed": True, "timestamped": True,
                             "timestamp_url": "https://tsa.example.com"}  # fmt: skip
    n = len(events_of(session, request))
    complete(session, T, request, signed=built, now=at(9))
    assert len(events_of(session, request)) == n and request.completed_at == at(3)


def test_complete_with_a_different_hash_is_a_conflict_and_other_states_are_not_ready(session, pdf_bytes):
    request, _ = signed_request(session, pdf_bytes)
    first = doc("b")
    complete(session, T, request, signed=first, now=at(3))
    with expect("hash_conflict"):
        complete(session, T, request, signed=doc("c"), now=at(4))
    assert request.signed_sha256 == first.sha256
    open_request, _ = one(session, pdf_bytes)
    with expect("not_ready"):
        complete(session, T, open_request, signed=doc(), now=at(4))


def test_delivery_and_download_are_recorded_without_changing_state(session, pdf_bytes):
    request, signer = signed_request(session, pdf_bytes)
    complete(session, T, request, signed=build_signed_pdf(session, T, request, pdf=pdf_bytes), now=at(4))
    record_delivery(session, T, request, channel="email", reference="msg-1", signer=signer, ctx=CTX, now=at(5))
    record_download(session, T, request, signer=signer, ctx=RequestContext(ip="198.51.100.2"), now=at(6))
    delivered, downloaded = events_of(session, request)[-2:]
    assert (delivered.kind, delivered.data, delivered.signer_id) == ("copy_delivered", {"channel": "email", "reference": "msg-1"}, signer.id)
    assert (downloaded.kind, downloaded.ip, downloaded.data) == ("downloaded", "198.51.100.2", {"document": "signed"})
    record_delivery(session, T, request, channel="mail", now=at(7))
    assert events_of(session, request)[-1].data == {"channel": "mail", "reference": None}
    assert request.status == "completed"


def test_build_after_complete_download_and_delivery_gives_the_same_pdf_and_complete_stays_a_no_op(session, pdf_bytes):
    request, _ = signed_request(session, pdf_bytes)
    first = build_signed_pdf(session, T, request, pdf=pdf_bytes)  # the real compose, no fakes
    complete(session, T, request, signed=first, now=at(3))
    record_download(session, T, request, ctx=CTX, now=at(4))
    record_delivery(session, T, request, channel="email", reference="r1", ctx=CTX, now=at(5))
    again = build_signed_pdf(session, T, request, pdf=pdf_bytes)
    assert again.sha256 == first.sha256 and again.pdf == first.pdf
    before = len(events_of(session, request))
    assert complete(session, T, request, signed=again, now=at(6)) is request
    assert len(events_of(session, request)) == before and request.completed_at == at(3)
