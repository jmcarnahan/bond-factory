"""Review round: date page rule, foreign signers, the caption cut, overdue flips, a second timeline-cutoff test."""

import io
from datetime import timedelta

import pytest
from conftest import CTX, NOW, T, at, events_of, expect, kinds_of, new_request, sign_it, signers_of
from pdf_samples import Text, make_pdf
from pypdf import PdfReader

from bond_esign import (
    AnchorRule,
    CertificateLabels,
    Placement,
    SignerSpec,
    build_signed_pdf,
    complete,
    record_delivery,
    record_download,
    record_sent,
)

TWO_PAGES = make_pdf([[Text(72, 500, "Accepted by")], [Text(72, 500, "Date of acceptance")]])


def test_a_date_anchor_on_another_page_is_dropped_and_listed(session):
    spec = SignerSpec("Pat Example", anchor=AnchorRule("Accepted by"), date_anchor=AnchorRule("Date of acceptance"))
    request = new_request(session, TWO_PAGES, signers=[spec])
    assert signers_of(session, request)[0].placement["page"] == 1
    assert signers_of(session, request)[0].date_placement is None
    assert events_of(session, request)[0].data["anchor_missing"] == ["Date of acceptance"]
    sign_it(session, signers_of(session, request)[0], TWO_PAGES)
    out = build_signed_pdf(session, T, request, pdf=TWO_PAGES)
    assert "2026" not in PdfReader(io.BytesIO(out.pdf)).pages[1].extract_text().replace("Date of acceptance", "")


def test_an_explicit_date_placement_on_another_page_is_refused(session, pdf_bytes):
    spec = SignerSpec("Pat Example", placement=Placement(1, 0.1, 0.1, 0.2, 0.05),
                      date_placement=Placement(2, 0.5, 0.1, 0.1, 0.02))
    with pytest.raises(ValueError, match="same page"):
        new_request(session, pdf_bytes, signers=[spec])


def test_a_date_anchor_without_a_signature_box_is_dropped(session):
    spec = SignerSpec("Pat Example", date_anchor=AnchorRule("Accepted by"))
    request = new_request(session, TWO_PAGES, signers=[spec])
    assert signers_of(session, request)[0].date_placement is None
    assert events_of(session, request)[0].data["anchor_missing"] == ["Accepted by"]


@pytest.mark.parametrize("call", ["sent", "delivery", "download"])
def test_a_signer_of_another_request_is_refused_before_any_write(session, pdf_bytes, call):
    request = new_request(session, pdf_bytes)
    other = signers_of(session, new_request(session, pdf_bytes, title="Other"))[0]
    before = kinds_of(session, request)
    with pytest.raises(ValueError, match="does not belong"):
        if call == "sent":
            record_sent(session, T, request, channel="email", signer=other, now=at(1))
        elif call == "delivery":
            record_delivery(session, T, request, channel="email", signer=other, now=at(1))
        else:
            record_download(session, T, request, document="original", signer=other, now=at(1))
    assert kinds_of(session, request) == before


def _caption_name(session, pdf, name):
    request = new_request(session, pdf, signers=[SignerSpec(name, placement=Placement(1, 0.1, 0.5, 0.3, 0.06))])
    sign_it(session, signers_of(session, request)[0], pdf, typed_name="Pat Example")
    out = build_signed_pdf(session, T, request, pdf=pdf)
    return PdfReader(io.BytesIO(out.pdf)).pages[0].extract_text()


def test_the_caption_cut_never_ends_on_a_combining_mark_or_a_space(session, pdf_bytes):
    marked = "A" * 38 + "é" + "xyz"  # the 40th character is the combining accent
    text = _caption_name(session, pdf_bytes, marked)
    assert "A" * 38 + "e..." in text and "́..." not in text
    spaced = "B" * 39 + " " + "Cdef"  # the cut would end on a space
    assert "B" * 39 + "..." in _caption_name(session, pdf_bytes, spaced)
    mark_41 = "C" * 40 + "́tail"  # the 41st character is a mark: the 40 kept stay whole
    assert "C" * 40 + "..." in _caption_name(session, pdf_bytes, mark_41)


def test_record_sent_on_an_overdue_request_keeps_the_expiry_flip(session, pdf_bytes):
    request = new_request(session, pdf_bytes, expires_at=NOW + timedelta(hours=1))
    with expect("expired"):
        record_sent(session, T, request, channel="email", now=at(61))
    assert request.status == "expired"
    assert kinds_of(session, request).count("expired") == 1
    assert "link_sent" not in kinds_of(session, request)


def test_a_download_before_signing_is_listed_but_one_after_the_last_signature_is_not(session, pdf_bytes):
    request = new_request(session, pdf_bytes)
    signer = signers_of(session, request)[0]
    record_download(session, T, request, document="original", ctx=CTX, now=at(0))
    sign_it(session, signer, pdf_bytes)
    first = build_signed_pdf(session, T, request, pdf=pdf_bytes, labels=CertificateLabels())
    with expect("not_open"):
        record_sent(session, T, request, channel="email", reminder=True, now=at(3))
    record_download(session, T, request, document="original", ctx=CTX, now=at(4))
    again = build_signed_pdf(session, T, request, pdf=pdf_bytes, labels=CertificateLabels())
    assert again.pdf == first.pdf
    complete(session, T, request, signed=first, now=at(5))
    pages = [p.extract_text() for p in PdfReader(io.BytesIO(first.pdf)).pages]
    text = "\n".join(pages)
    assert text.count("Original document downloaded") == 1  # the first one only
    assert kinds_of(session, request).count("downloaded") == 2  # both are in the log, only one on the page
