import io
from pathlib import Path

import pytest
from pdf_samples import Text, make_pdf, text_width
from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject

from bond_esign.anchor import find_anchor
from bond_esign.errors import INVALID_PDF, EsignError
from bond_esign.types import AnchorRule

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "esign" / "weasy_acceptance.pdf"
PHRASE = "Accepted by (customer)"


def test_phrase_split_into_two_runs_is_found():
    pdf = make_pdf([[Text(72, 300, PHRASE, 11, split_at=11)]])
    found = find_anchor(pdf, AnchorRule(PHRASE))
    assert found is not None and found.page == 1
    right = 72 + text_width(PHRASE)
    assert found.x == pytest.approx(right / 612 + 0.01, abs=0.003)
    assert found.y == pytest.approx(1 - 300 / 792 - 0.045, abs=0.003)


def test_absent_is_none():
    assert find_anchor(make_pdf([[Text(72, 300, "nothing here")]]), AnchorRule(PHRASE)) is None


def test_garbage_is_invalid_pdf():
    with pytest.raises(EsignError) as err:
        find_anchor(b"nope", AnchorRule(PHRASE))
    assert err.value.code == INVALID_PDF


def test_occurrence_first_and_last_over_pages():
    pdf = make_pdf([[Text(72, 600, PHRASE)], [Text(72, 200, "x")], [Text(72, 300, PHRASE)]])
    first = find_anchor(pdf, AnchorRule(PHRASE, occurrence=0))
    last = find_anchor(pdf, AnchorRule(PHRASE))
    assert (first.page, last.page) == (1, 3)
    assert find_anchor(pdf, AnchorRule(PHRASE, occurrence=1)).page == 3
    assert find_anchor(pdf, AnchorRule(PHRASE, occurrence=2)) is None
    assert find_anchor(pdf, AnchorRule(PHRASE, occurrence=-3)) is None


def test_reading_order_within_a_page_is_top_to_bottom():
    pdf = make_pdf([[Text(72, 100, PHRASE), Text(72, 700, PHRASE)]])
    top = find_anchor(pdf, AnchorRule(PHRASE, occurrence=0))
    bottom = find_anchor(pdf, AnchorRule(PHRASE, occurrence=1))
    assert top.y < bottom.y


def test_case_sensitivity_and_whitespace():
    pdf = make_pdf([[Text(72, 300, "Accepted   by (Customer)")]])
    assert find_anchor(pdf, AnchorRule("accepted by (customer)")) is not None
    assert find_anchor(pdf, AnchorRule("accepted by (customer)", case_sensitive=True)) is None
    assert find_anchor(pdf, AnchorRule("Accepted by (Customer)", case_sensitive=True)) is not None


def test_direction_is_pinned_top_origin():
    top = find_anchor(make_pdf([[Text(72, 760, PHRASE)]]), AnchorRule(PHRASE))
    bottom = find_anchor(make_pdf([[Text(72, 60, PHRASE)]]), AnchorRule(PHRASE))
    assert top.y < 0.1
    assert bottom.y > 0.85
    assert 0 <= bottom.y <= 1 - bottom.h  # clamped into the page


def test_mediabox_not_at_origin():
    src = PdfReader(io.BytesIO(make_pdf([[Text(200, 400, PHRASE)]])))
    writer = PdfWriter()
    writer.add_page(src.pages[0])
    writer.pages[0].mediabox = RectangleObject([100, 50, 712, 842])
    buf = io.BytesIO()
    writer.write(buf)
    found = find_anchor(buf.getvalue(), AnchorRule(PHRASE))
    right = 200 + text_width(PHRASE)
    assert found.x == pytest.approx((right - 100) / 612 + 0.01, abs=0.003)
    assert found.y == pytest.approx(1 - (400 - 50) / 792 - 0.045, abs=0.003)


def test_rotated_pages_are_skipped():
    src = PdfReader(io.BytesIO(make_pdf([[Text(72, 300, PHRASE)]])))
    writer = PdfWriter()
    writer.add_page(src.pages[0])
    writer.pages[0].rotate(90)
    buf = io.BytesIO()
    writer.write(buf)
    assert find_anchor(buf.getvalue(), AnchorRule(PHRASE)) is None


def test_weasyprint_fixture():
    """Measured once from the fixture: the ruled line spans x 0.2745..0.7062 at y 0.3935 (page fractions);
    the label 'Date' starts at x 0.7062."""
    found = find_anchor(FIXTURE.read_bytes(), AnchorRule(PHRASE))
    assert found is not None and found.page == 1
    assert found.x == pytest.approx(0.2747, abs=0.006)  # right of the label, at the start of the line
    assert found.y == pytest.approx(0.3456, abs=0.006)
    assert found.x + found.w < 0.7062  # left of the "Date" label
    bottom = found.y + found.h
    assert abs(bottom - 0.3935) < 0.015  # the box bottom sits on the ruled line
