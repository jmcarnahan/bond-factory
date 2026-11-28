"""Readiness round: record_sent, guarded delivery and download, app_link, record_view, key cleaning."""

import io

import pytest
from conftest import CTX, NOW, PLACEMENT, T, at, events_of, expect, kinds_of, new_request, sign_it, signers_of
from pypdf import PdfReader

from bond_esign import (
    CertificateLabels,
    SignerSpec,
    build_signed_pdf,
    complete,
    decline,
    find_signer_by_key,
    record_delivery,
    record_download,
    record_sent,
    signing_view,
    void,
)
from bond_esign.types import CertificateEvent
from bond_esign.verify import verify_evidence


def one(session, pdf, **kw):
    request = new_request(session, pdf, **kw)
    return request, signers_of(session, request)[0]


def test_record_sent_writes_link_sent_then_reminder_sent(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    record_sent(session, T, request, channel="email", reference="msg-1", signer=signer, ctx=CTX, now=at(1))
    record_sent(session, T, request, channel="sms", reminder=True, signer=signer, now=at(2))
    first, second = events_of(session, request)[-2:]
    assert (first.kind, first.data, first.signer_id, first.ip) == (
        "link_sent", {"channel": "email", "reference": "msg-1"}, signer.id, CTX.ip)
    assert (second.kind, second.data) == ("reminder_sent", {"channel": "sms", "reference": None})
    assert request.status == "open" and verify_evidence(session, T, request).ok


def test_record_sent_cleans_and_cuts_its_text(session, pdf_bytes):
    request, _ = one(session, pdf_bytes)
    record_sent(session, T, request, channel="e\x00mail" + "x" * 300, reference="r" * 900, now=at(1))
    data = events_of(session, request)[-1].data
    assert data["channel"].startswith("email") and len(data["channel"]) == 200 and len(data["reference"]) == 500


@pytest.mark.parametrize("how", ["signed", "voided", "declined"])
def test_record_sent_is_refused_unless_open(session, pdf_bytes, how):
    request, signer = one(session, pdf_bytes)
    if how == "signed":
        sign_it(session, signer, pdf_bytes)
    elif how == "voided":
        void(session, T, request, reason="x", ctx=None, now=at(1))
    else:
        decline(session, T, signer, reason=None, ctx=None, now=at(1))
    before = kinds_of(session, request)
    with expect("not_open"):
        record_sent(session, T, request, channel="email", now=at(2))
    assert kinds_of(session, request) == before


def test_record_sent_on_an_overdue_request_expires_it_and_raises(session, pdf_bytes):
    from datetime import timedelta

    request, _ = one(session, pdf_bytes, expires_at=NOW + timedelta(hours=1))
    with expect("expired"):
        record_sent(session, T, request, channel="email", now=at(61))
    assert request.status == "expired" and kinds_of(session, request)[-1] == "expired"
    with expect("expired"):
        record_sent(session, T, request, channel="email", reminder=True, now=at(62))


def test_record_delivery_needs_a_completed_request(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    with expect("not_ready"):
        record_delivery(session, T, request, channel="email", now=at(1))
    assert "copy_delivered" not in kinds_of(session, request)
    sign_it(session, signer, pdf_bytes)
    with expect("not_ready"):  # signed is not enough: no signed copy exists before complete()
        record_delivery(session, T, request, channel="email", now=at(2))
    complete(session, T, request, signed=build_signed_pdf(session, T, request, pdf=pdf_bytes), now=at(3))
    record_delivery(session, T, request, channel="em\x00ail", ctx=CTX, now=at(4))
    assert events_of(session, request)[-1].data == {"channel": "email", "reference": None}


def test_record_download_signed_needs_a_completed_request_original_does_not(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    with expect("not_ready"):
        record_download(session, T, request, now=at(1))
    with expect("not_ready"):
        record_download(session, T, request, document="signed", now=at(1))
    record_download(session, T, request, document="original", ctx=CTX, now=at(2))
    assert events_of(session, request)[-1].data == {"document": "original"}
    sign_it(session, signer, pdf_bytes)
    with expect("not_ready"):
        record_download(session, T, request, now=at(3))
    complete(session, T, request, signed=build_signed_pdf(session, T, request, pdf=pdf_bytes), now=at(3))
    record_download(session, T, request, now=at(4))
    assert events_of(session, request)[-1].data == {"document": "signed"}
    assert kinds_of(session, request).count("downloaded") == 2


def test_record_download_refuses_an_unknown_document_and_writes_nothing(session, pdf_bytes):
    request, _ = one(session, pdf_bytes)
    before = kinds_of(session, request)
    for bad in ("both", "", "Signed", None):
        with pytest.raises(ValueError, match="document"):
            record_download(session, T, request, document=bad, now=at(1))
    assert kinds_of(session, request) == before


def test_timeline_names_the_document_downloaded(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    record_download(session, T, request, document="original", now=at(0))
    sign_it(session, signer, pdf_bytes)
    for labels, want in ((CertificateLabels(), "Original document downloaded"),
                         (CertificateLabels.spanish(), "Documento original descargado")):
        out = build_signed_pdf(session, T, request, pdf=pdf_bytes, labels=labels)
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(out.pdf)).pages)
        assert want in text
    # an old download event (no detail) prints as the signed copy
    from cert_samples import data

    from bond_esign.certificate import certificate_pages

    page = certificate_pages(data(events=[CertificateEvent(1, NOW, "downloaded")]), labels=CertificateLabels())
    assert "Signed copy downloaded" in PdfReader(io.BytesIO(page)).pages[0].extract_text()


def test_an_old_downloaded_event_without_a_document_reads_as_the_signed_copy():
    labels = CertificateLabels()
    assert labels.event_label("downloaded", None) == "Signed copy downloaded"
    assert labels.event_label("downloaded", "original") == "Original document downloaded"
    assert labels.event_label("downloaded", "other") == "Signed copy downloaded"
    assert labels.event_label("created", "x") == "Request created"
    assert CertificateEvent(1, NOW, "downloaded").detail is None
    assert CertificateLabels.spanish().event_label("link_sent") == "Enlace de firma enviado"
    assert CertificateLabels.spanish().event_label("reminder_sent") == "Recordatorio enviado"
    assert (labels.event_label("link_sent"), labels.event_label("reminder_sent")) == (
        "Signing link sent", "Reminder sent")


def test_the_method_heading_and_labels():
    en, es = CertificateLabels(), CertificateLabels.spanish()
    assert (en.method, es.method) == ("Signed via", "Firmado mediante")
    assert en.method_label("app_link") == "Private link issued by the sender"
    assert es.method_label("app_link") == "Enlace privado emitido por el remitente"
    assert en.method_label("link") == "Private signing link"


def test_an_app_link_signature_is_recorded_and_passes_verify_evidence(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes, method="app_link")
    assert signer.method == "app_link" and events_of(session, request)[-1].data["method"] == "app_link"
    assert verify_evidence(session, T, request).ok
    assert build_signed_pdf(session, T, request, pdf=pdf_bytes).pages > 2  # the certificate prints it


def test_app_link_follows_the_link_code_rule(session, pdf_bytes):
    from bond_esign import Policy

    _, signer = one(session, pdf_bytes, policy=Policy(require_email_code=True))
    with expect("code_required"):
        sign_it(session, signer, pdf_bytes, method="app_link")
    with pytest.raises(ValueError):
        sign_it(session, signer, pdf_bytes, method="made_up")


def test_record_view_false_writes_no_viewed_event(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    before = kinds_of(session, request)
    view = signing_view(session, T, signer, ctx=CTX, now=at(1), record_view=False)
    assert view.can_sign and kinds_of(session, request) == before
    signing_view(session, T, signer, ctx=CTX, now=at(2))
    assert kinds_of(session, request) == [*before, "viewed"]
    signing_view(session, T, signer, ctx=CTX, now=at(3), record_view=False)
    assert kinds_of(session, request).count("viewed") == 1


def test_find_signer_by_key_cleans_the_key_the_way_it_was_stored(session, pdf_bytes):
    request = new_request(session, pdf_bytes, signers=[SignerSpec("Pat Example", key="c\x00-1\x07")])
    stored = signers_of(session, request)[0]
    assert stored.key == "c-1"
    assert find_signer_by_key(session, T, request.id, "c\x00-1\x07") is stored
    assert find_signer_by_key(session, T, request.id, "c-1") is stored
    assert find_signer_by_key(session, T, request.id, "\x00\x01") is None
    assert find_signer_by_key(session, T, request.id, "c-2") is None


def _rebuilt_matches(session, request, pdf):
    again = build_signed_pdf(session, T, request, pdf=pdf)
    assert again.sha256 == request.signed_sha256 and again.pdf is not None
    return again


def test_an_event_between_the_last_signature_and_complete_does_not_change_a_rebuild(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes)
    record_download(session, T, request, document="original", now=at(2))
    first = build_signed_pdf(session, T, request, pdf=pdf_bytes)
    complete(session, T, request, signed=first, now=at(3))
    _rebuilt_matches(session, request, pdf_bytes)


def test_an_event_after_build_but_before_complete_does_not_change_a_rebuild(session, pdf_bytes):
    request, signer = one(session, pdf_bytes)
    sign_it(session, signer, pdf_bytes)
    first = build_signed_pdf(session, T, request, pdf=pdf_bytes)
    record_download(session, T, request, document="original", now=at(2))
    complete(session, T, request, signed=first, now=at(3))
    again = _rebuilt_matches(session, request, pdf_bytes)
    assert again.pdf == first.pdf


def test_with_two_signers_the_cutoff_is_the_second_signature(session, pdf_bytes):
    from bond_esign.verify import verify_evidence as _ve

    request = new_request(session, pdf_bytes, signers=[SignerSpec("Pat Example", placement=PLACEMENT),
                                                       SignerSpec("Sam Sample", placement=PLACEMENT)])
    one_, two = signers_of(session, request)
    sign_it(session, one_, pdf_bytes, now=at(1))
    signing_view(session, T, two, ctx=CTX, now=at(2))
    record_sent(session, T, request, channel="email", reminder=True, signer=two, now=at(3))
    sign_it(session, two, pdf_bytes, typed_name="Sam Sample", now=at(4))
    record_download(session, T, request, document="original", now=at(5))
    first = build_signed_pdf(session, T, request, pdf=pdf_bytes, labels=CertificateLabels())
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(first.pdf)).pages)
    assert "Reminder sent" in text and "Document viewed" in text and "Original document downloaded" not in text
    complete(session, T, request, signed=first, now=at(6))
    assert build_signed_pdf(session, T, request, pdf=pdf_bytes).pdf == first.pdf and _ve(session, T, request).ok
