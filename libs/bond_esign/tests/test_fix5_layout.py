"""Readiness round: date_anchor, the 40-character caption name and text outside cp1252 with a TTF."""

import io
import os
from pathlib import Path

from conftest import T, events_of, new_request, sig_png, sign_it, signers_of
from pypdf import PdfReader
from reportlab.pdfbase.pdfmetrics import stringWidth

from bond_esign import AnchorRule, Brand, Placement, SignerSpec, build_signed_pdf
from bond_esign._text import font_for, safe

WEASY = (Path(__file__).resolve().parents[3] / "fixtures" / "esign" / "weasy_acceptance.pdf").read_bytes()
SIGN_RULE = AnchorRule("Accepted by (customer)")
# The template's "Date" label shares one text run with "Accepted by (customer)", so "Date" alone cannot be
# anchored. Anchor on the phrase instead: dx puts the box right of the "Date" label (label ends near x=456pt,
# its ruled blank runs from 462 to 561pt), dy/h keep the box on the label row.
DATE_RULE = AnchorRule("Accepted by (customer)", dx=0.505, dy=-0.014, w=0.12, h=0.02)
LABEL_BASELINE, LABEL_RULE_Y, DATE_LABEL_RIGHT = 427.25, 422.95, 456.0


def runs(pdf: bytes, index: int = 0):
    found = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            found.append((text.strip(), tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

    PdfReader(io.BytesIO(pdf)).pages[index].extract_text(visitor_text=visit)
    return found


def test_date_anchor_lands_in_the_date_blank_on_the_signature_row(session):
    spec = SignerSpec("Pat Example", anchor=SIGN_RULE, date_anchor=DATE_RULE)
    request = new_request(session, WEASY, signers=[spec])
    signer = signers_of(session, request)[0]
    assert signer.date_placement is not None and signer.date_placement["page"] == 1
    sign_it(session, signer, WEASY)
    out = build_signed_pdf(session, T, request, pdf=WEASY)
    (_, x, y) = next(r for r in runs(out.pdf) if r[0] == "Nov 8, 2026")
    assert x > DATE_LABEL_RIGHT and x + stringWidth("Nov 8, 2026", "Helvetica", 10) < 0.9176 * 612
    assert abs(y - LABEL_BASELINE) < 6 and abs(y - LABEL_RULE_Y) < 6
    (_, _, sig_y) = next(r for r in runs(out.pdf) if r[0] == "Pat Example")
    assert abs(sig_y - y) < 25  # the signature stands on the same row


def test_date_placement_wins_over_date_anchor(session, pdf_bytes):
    box = Placement(1, 0.5, 0.5, 0.1, 0.02)
    spec = SignerSpec("Pat Example", placement=Placement(1, 0.1, 0.1, 0.2, 0.05), date_placement=box,
                      date_anchor=AnchorRule("not in this file"))
    request = new_request(session, pdf_bytes, signers=[spec])
    assert signers_of(session, request)[0].date_placement == {"page": 1, "x": 0.5, "y": 0.5, "w": 0.1, "h": 0.02}
    assert "anchor_missing" not in events_of(session, request)[0].data


def test_a_date_anchor_that_is_not_found_is_recorded_like_a_missing_signature_anchor(session, pdf_bytes):
    spec = SignerSpec("Pat Example", date_anchor=AnchorRule("Date of acceptance"))
    request = new_request(session, pdf_bytes, signers=[spec])
    assert signers_of(session, request)[0].date_placement is None
    assert events_of(session, request)[0].data["anchor_missing"] == ["Date of acceptance"]


def test_a_long_name_is_cut_to_40_characters_in_the_caption_only(session, pdf_bytes):
    name = "Alexandria Bartholomew Montgomery-Fitzgerald Jr"
    request = new_request(session, pdf_bytes, signers=[SignerSpec(name, placement=Placement(1, 0.1, 0.5, 0.3, 0.06))])
    sign_it(session, signers_of(session, request)[0], pdf_bytes, typed_name="Pat Example")
    out = build_signed_pdf(session, T, request, pdf=pdf_bytes)
    reader = PdfReader(io.BytesIO(out.pdf))
    page_one, cert = reader.pages[0].extract_text(), "".join(p.extract_text() for p in reader.pages[2:])
    assert f"{name[:40]}..." in page_one and name not in page_one
    assert name in cert.replace("\n", " ")


VERA = os.path.join(os.path.dirname(__import__("reportlab").__file__), "fonts", "Vera.ttf")
NAME = "Łukasz Čapek Šóć"


def test_font_for_keeps_the_default_when_it_can_draw_the_text():
    assert font_for("Pat Example", "Helvetica", VERA) == ("Helvetica", "Pat Example")
    assert font_for("Zoë Müller", "Helvetica", None) == ("Helvetica", "Zoë Müller")
    assert font_for(NAME, "Helvetica", None) == ("Helvetica", safe(NAME)) and "?" in safe(NAME)
    font, text = font_for("Ł\r\nx\ty", "Helvetica", VERA)
    assert font.startswith("BondEsignTTF") and text == "Ł  x y"


def _build(session, pdf, brand):
    request = new_request(session, pdf, signers=[SignerSpec(NAME, placement=Placement(1, 0.1, 0.5, 0.4, 0.08))])
    sign_it(session, signers_of(session, request)[0], pdf, typed_name=None, drawn_png=sig_png())
    return request, build_signed_pdf(session, T, request, pdf=pdf, brand=brand)


def test_a_ttf_draws_names_outside_cp1252_in_the_caption_and_the_certificate(session, pdf_bytes):
    request, out = _build(session, pdf_bytes, Brand(font_path=VERA))
    pages = [p.extract_text() for p in PdfReader(io.BytesIO(out.pdf)).pages]
    assert NAME in pages[0] and "?" not in pages[0]
    cert = "\n".join(pages[2:])
    assert cert.count(NAME) >= 2 and "?" not in cert  # the signer block and the timeline row
    assert build_signed_pdf(session, T, request, pdf=pdf_bytes, brand=Brand(font_path=VERA)).pdf == out.pdf  # deterministic with the font


def test_without_a_ttf_the_old_question_mark_behaviour_is_unchanged(session, pdf_bytes):
    _, out = _build(session, pdf_bytes, None)
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(out.pdf)).pages)
    assert "?ukasz" in text
    assert NAME not in text
