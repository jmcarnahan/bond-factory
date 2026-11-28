import io

import pytest
from pdf_samples import Text, make_pdf, make_png
from pypdf import PdfReader

from bond_esign.errors import NAME_NOT_RENDERABLE, EsignError
from bond_esign.stamping import stamp
from bond_esign.types import Placement, Stamp

BOX = Placement(1, 0.3, 0.4, 0.3, 0.055)


def _pdf():
    return make_pdf([[Text(72, 700, "First page text")], [Text(72, 700, "Second page text")]])


def _content(pdf: bytes, index: int) -> bytes:
    return PdfReader(io.BytesIO(pdf)).pages[index].get_contents().get_data()


def test_image_stamp_keeps_text_and_adds_image():
    out = stamp(_pdf(), [Stamp(BOX, png=make_png(), caption="Signed electronically by Pat Example, Nov 27, 2026, ref ab12cd34")])
    reader = PdfReader(io.BytesIO(out))
    assert len(reader.pages) == 2
    text = reader.pages[0].extract_text()
    assert "First page text" in text and "Signed electronically by Pat Example" in text
    assert len(reader.pages[0].images) == 1
    assert len(reader.pages[1].images) == 0


def test_untouched_page_content_is_identical():
    src = _pdf()
    out = stamp(src, [Stamp(BOX, png=make_png())])
    assert _content(out, 1) == _content(src, 1)
    assert _content(out, 0) != _content(src, 0)


def test_typed_name_and_date_text_extractable():
    date_box = Placement(1, 0.7, 0.4, 0.2, 0.04)
    out = stamp(_pdf(), [Stamp(BOX, typed_name="Pat Example", date_text="Nov 27, 2026", date_placement=date_box)])
    text = PdfReader(io.BytesIO(out)).pages[0].extract_text()
    assert "Pat Example" in text and "Nov 27, 2026" in text and "First page text" in text


def test_negative_page_counts_from_end():
    out = stamp(_pdf(), [Stamp(Placement(-1, 0.3, 0.4, 0.3, 0.055), typed_name="Pat Example")])
    reader = PdfReader(io.BytesIO(out))
    assert "Pat Example" not in reader.pages[0].extract_text()
    assert "Pat Example" in reader.pages[1].extract_text()


def test_not_renderable_name_without_font():
    with pytest.raises(EsignError) as err:
        stamp(_pdf(), [Stamp(BOX, typed_name="张伟")])
    assert err.value.code == NAME_NOT_RENDERABLE


def test_latin1_accents_render():
    out = stamp(_pdf(), [Stamp(BOX, typed_name="José Peña")])
    assert "Jos" in PdfReader(io.BytesIO(out)).pages[0].extract_text()


def test_png_transparency_is_masked_and_output_is_deterministic():
    stamps = [Stamp(BOX, png=make_png(alpha=True), caption="c")]
    a, b = stamp(_pdf(), stamps), stamp(_pdf(), stamps)
    assert a == b
    xobjects = PdfReader(io.BytesIO(a)).pages[0]["/Resources"]["/XObject"]
    assert any("/SMask" in x.get_object() for x in xobjects.values())


def test_caption_is_truncated_to_the_page():
    long = "x" * 400
    out = stamp(_pdf(), [Stamp(Placement(1, 0.7, 0.4, 0.25, 0.055), typed_name="Pat", caption=long)])
    text = PdfReader(io.BytesIO(out)).pages[0].extract_text()
    assert 0 < text.count("x") < 400


def test_page_out_of_range():
    with pytest.raises(EsignError):
        stamp(_pdf(), [Stamp(Placement(5, 0.3, 0.4, 0.3, 0.05), typed_name="Pat")])


def _runs(pdf: bytes):
    runs = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            runs.append((text.strip(), tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

    PdfReader(io.BytesIO(pdf)).pages[0].extract_text(visitor_text=visit)
    return runs


# Measured once per fixture (see FIXTURES in test_anchor.py): label baseline and the ruled line's upper edge, PDF points.
WEASY = {"weasy_acceptance.pdf": 422.95, "weasy_acceptance_tight.pdf": 480.35}


@pytest.mark.parametrize("name", sorted(WEASY))
def test_caption_sits_between_the_ruled_line_and_the_next_row_in_the_weasy_fixtures(name):
    from pathlib import Path

    from bond_esign.anchor import find_anchor
    from bond_esign.stamping import _BAND, _CAPTION_SIZE
    from bond_esign.types import AnchorRule

    src = (Path(__file__).resolve().parents[3] / "fixtures" / "esign" / name).read_bytes()
    place = find_anchor(src, AnchorRule("Accepted by (customer)"))
    out = stamp(src, [Stamp(place, png=make_png(), caption="Signed electronically by Pat Example, ref ab12cd34")])
    runs = _runs(out)
    caption = next(v for t, v in runs if t.startswith("Signed electronically"))
    next_row = next(v for t, v in runs if t.startswith("For Sample Company"))
    line = WEASY[name]
    assert caption + 0.72 * _CAPTION_SIZE <= line - 1  # the caption's glyph top is clear below the ruled line
    assert caption >= next_row + 0.72 * 10 + 1  # and its baseline is above the next row's text top
    bottom = (1 - place.y - place.h) * 792
    assert abs(bottom + _BAND - line) < 4  # the signature area ends on the line


def test_caption_takes_a_band_inside_the_box_and_no_caption_uses_the_whole_box():
    from bond_esign.stamping import _BAND

    box = Placement(1, 0.3, 0.4, 0.3, 0.055)  # bottom of the box is at y = 792 * (1 - 0.455) = 431.6
    height = 0.055 * 792
    with_caption = _runs(_overlay_pdf([Stamp(box, typed_name="Pat", caption="cap")]))
    plain = _runs(_overlay_pdf([Stamp(box, typed_name="Pat")]))
    cap_y = next(v for t, v in with_caption if t == "cap")
    name_with = next(v for t, v in with_caption if t == "Pat")
    name_plain = next(v for t, v in plain if t == "Pat")
    bottom = 792 * (1 - 0.455)
    assert cap_y == pytest.approx(bottom + 0.5, abs=0.01)
    assert name_plain == pytest.approx(bottom + 0.2 * height, abs=0.01)
    assert name_with == pytest.approx(bottom + _BAND + 0.2 * (height - _BAND), abs=0.01)


def _overlay_pdf(items):
    return stamp(make_pdf([[]]), items)


def _text_runs(pdf: bytes, index: int = 0):
    found = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            found.append((text.strip(), tm[4] * cm[0] + tm[5] * cm[2] + cm[4], tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

    PdfReader(io.BytesIO(pdf)).pages[index].extract_text(visitor_text=visit)
    return found


def _cropped(rotate: int = 0) -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_pdf())))
    writer.pages[0].cropbox = RectangleObject((100, 50, 500, 700))
    if rotate:
        writer.pages[0].rotate(rotate)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_placement_fractions_are_of_the_cropbox_when_there_is_one():
    out = stamp(_cropped(), [Stamp(Placement(1, 0.5, 0.5, 0.3, 0.1), typed_name="Pat Example")])
    (_, x, y) = next(r for r in _text_runs(out) if r[0] == "Pat Example")
    assert x == pytest.approx(100 + 0.5 * 400, abs=0.5)  # left edge 100 + half of the 400-wide visible page
    top_of_box = 700 - 0.5 * 650  # y fraction counts from the visible top (700)
    assert top_of_box - 0.1 * 650 <= y <= top_of_box


def test_a_found_anchor_stamps_where_it_was_found_on_a_cropped_page():
    from pdf_samples import text_width

    from bond_esign.anchor import find_anchor
    from bond_esign.types import AnchorRule

    phrase = "Accepted by (customer)"
    src = PdfReader(io.BytesIO(make_pdf([[Text(150, 300, phrase)]])))
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject

    writer = PdfWriter(clone_from=src)
    writer.pages[0].cropbox = RectangleObject((100, 50, 500, 700))
    buf = io.BytesIO()
    writer.write(buf)
    pdf = buf.getvalue()
    box = find_anchor(pdf, AnchorRule(phrase, dx=0.0))
    out = stamp(pdf, [Stamp(box, typed_name="Pat Example")])
    (_, x, _) = next(r for r in _text_runs(out) if r[0] == "Pat Example")
    assert x == pytest.approx(150 + text_width(phrase), abs=1.0)


def test_a_stamp_on_a_rotated_page_is_refused():
    with pytest.raises(ValueError, match="rotated pages are not supported"):
        stamp(_cropped(rotate=90), [Stamp(BOX, typed_name="Pat Example")])
    assert stamp(_cropped(rotate=90), [Stamp(Placement(2, 0.3, 0.4, 0.3, 0.055), typed_name="Pat Example")])
