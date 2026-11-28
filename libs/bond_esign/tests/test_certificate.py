import io
from datetime import datetime

from cert_samples import HEAD, data, signer
from pypdf import PdfReader

from bond_esign.certificate import certificate_pages
from bond_esign.labels import CertificateLabels
from bond_esign.types import Brand, CertificateEvent

EN = CertificateLabels()


def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def _flat(pdf: bytes) -> str:
    return "".join(_text(pdf).split())


def test_one_signer_one_page_with_every_field():
    pdf = certificate_pages(data(), labels=EN, brand=None)
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1
    assert (float(reader.pages[0].mediabox.width), float(reader.pages[0].mediabox.height)) == (612, 792)
    text, flat = _text(pdf), _flat(pdf)
    for want in ("Signature certificate", "Sample estimate 100", "req-0001", "Pat Example", "pat@example.com",
                 "customer", "Private signing link", "203.0.113.7", "2026-11-27 18:30:05 UTC",
                 "bond-esign-consent/1", "Page 1 of 1", "How to verify", "Signed", "Request created",
                 "I agree to sign this document electronically."):  # fmt: skip
        assert want in text, want
    for want in ("ef" * 32, "12" * 32, HEAD, "cd" * 32):
        assert want in flat


def test_user_agent_trimmed_to_120():
    flat = _flat(certificate_pages(data(), labels=EN, brand=None))
    assert "UA/1.0" + "x" * 113 in flat  # 120 chars total: "UA/1.0 " (7) + 113 x
    assert "x" * 114 not in flat


def test_zone_adds_local_time():
    flat = _text(certificate_pages(data(zone="America/Los_Angeles"), labels=EN, brand=None))
    assert "2026-11-27 18:30:05 UTC" in flat and "2026-11-27 10:30:05 PST" in flat
    assert "America/Los_Angeles" in flat


def test_many_events_and_long_consent_overflow():
    events = [CertificateEvent(i, datetime(2026, 11, 27, 18, 0, i % 60), "viewed", "Pat Example") for i in range(1, 41)]
    pdf = certificate_pages(data(events=events, consent_text="word " * 1200), labels=EN, brand=None)
    n = len(PdfReader(io.BytesIO(pdf)).pages)
    assert n >= 2
    assert f"Page {n} of {n}" in _text(pdf) and "Page 1 of " + str(n) in _text(pdf)
    assert "40" in _text(pdf)


def test_hostile_and_unencodable_names():
    pdf = certificate_pages(data(signers=[signer("<b>x</b> & <i>y</i>"), signer("张伟", kind="typed")]),
                            labels=EN, brand=None)  # fmt: skip
    text = _text(pdf)
    assert "<b>x</b> & <i>y</i>" in text
    assert "??" in text


def test_drawn_signature_embedded():
    pdf = certificate_pages(data(signers=[signer(kind="drawn")]), labels=EN, brand=None)
    assert len(PdfReader(io.BytesIO(pdf)).pages[0].images) == 1


def test_brand_logo_and_accent():
    from pdf_samples import make_png

    brand = Brand(name="Sample Company", logo_png=make_png(), accent_rgb=(200, 30, 30))
    pdf = certificate_pages(data(), labels=EN, brand=brand)
    reader = PdfReader(io.BytesIO(pdf))
    assert "Sample Company" in _text(pdf) and len(reader.pages[0].images) == 1
    assert b".784314 .117647 .117647" in reader.pages[0].get_contents().get_data()


def test_spanish_labels():
    text = _text(certificate_pages(data(), labels=CertificateLabels.spanish(), brand=None))
    assert "Certificado de firma" in text and "Pagina 1 de 1" in text and "Firmado" in text
    assert "Enlace de firma privado" in text


def test_same_input_same_bytes():
    assert certificate_pages(data(), labels=EN, brand=None) == certificate_pages(data(), labels=EN, brand=None)


def test_value_column_starts_after_the_widest_label_in_both_languages():
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from bond_esign.certificate_draw import Flow, label_names, value_offset

    for labels in (EN, CertificateLabels.spanish()):
        offset = value_offset(labels)
        assert all(stringWidth(n, "Helvetica", 9) < offset for n in label_names(labels))
        assert Flow(labels, None, None).lw == offset


def test_hash_values_never_run_off_the_page():
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from bond_esign.certificate_draw import WIDTH, value_offset

    for labels in (EN, CertificateLabels.spanish()):
        assert stringWidth("ab" * 32, "Courier", 5.5) < WIDTH - 8 - value_offset(labels)
    flat = _flat(certificate_pages(data(), labels=CertificateLabels.spanish(), brand=None))
    assert "ef" * 32 in flat and "cd" * 32 in flat


def test_the_consent_hash_has_its_own_clear_label_in_both_languages():
    for labels, label in ((EN, "Consent SHA-256"), (CertificateLabels.spanish(), "SHA-256 del consentimiento")):
        assert labels.consent_sha256 == label
        assert "".join(label.split()) in _flat(certificate_pages(data(), labels=labels, brand=None))


def test_a_drawn_signature_image_has_clear_space_above_and_below():
    from pdf_samples import make_png

    from bond_esign.certificate_draw import Flow

    f = Flow(EN, None, None)
    f.field("Signature", "Drawn signature", indent=8)
    top = f.y
    f.image(make_png(240, 80), 180, 56, indent=120)
    height = min(56.0, 180 * 80 / 240)  # limited by the 56pt maximum height
    assert top - f.y >= height + 8  # at least 4pt above and 4pt below


def test_worst_case_unbroken_values_build_quickly_and_are_cut_to_the_field_maximum():
    import time

    from bond_esign.certificate_draw import FIELD_MAX, WIDTH, wrap

    big = data(signers=[signer("N" * 500, kind="typed")])
    s = big.signers[0]
    s = type(s)(**{**s.__dict__, "ip": "1" * 64, "user_agent": "U" * 1000, "email": "e" * 500})
    big = data(signers=[s], consent_text="C" * 20_000)
    started = time.perf_counter()
    pdf = certificate_pages(big, labels=EN, brand=None)
    assert time.perf_counter() - started < 2.0 and pdf.startswith(b"%PDF")
    flat = _flat(pdf)
    assert "U" * 120 in flat and "U" * 121 not in flat  # the device line keeps its own 120-character cap
    assert "e" * FIELD_MAX in flat and "e" * (FIELD_MAX + 1) not in flat
    assert "C" * 20_000 not in flat and flat.count("C") >= 19_000  # the consent text is wrapped, not cut
    lines = wrap("x" * 3000, "Helvetica", 9.0, WIDTH)
    assert "".join(lines) == "x" * 3000 and len(lines) > 1
    started = time.perf_counter()
    wrap("W" * 100_000, "Helvetica", 9.0, 100.0)
    assert time.perf_counter() - started < 2.0
