"""The sample PDF's ruled line: the signature stands on it and the caption prints under it, not over it."""

import io

from bond_esign import AnchorRule, Placement, Stamp
from bond_esign.anchor import find_anchor
from bond_esign.stamping import _BAND, _CAPTION_SIZE, stamp
from pypdf import PdfReader

from sdk_example.esign_sample import ANCHOR_TEXT, LINE_BELOW, LINE_Y, sample_pdf

PAGE_H = 792.0


def _runs(pdf: bytes, index: int) -> list[tuple[str, float]]:
    found: list[tuple[str, float]] = []

    def visit(text, cm, tm, font_dict, font_size):
        if text.strip():
            found.append((text.strip(), tm[4] * cm[1] + tm[5] * cm[3] + cm[5]))

    PdfReader(io.BytesIO(pdf)).pages[index].extract_text(visitor_text=visit)
    return found


def test_the_ruled_line_is_below_the_label_and_the_caption_is_below_the_line():
    pdf = sample_pdf()
    line_y = LINE_Y - LINE_BELOW  # PDF coordinates of the ruled line
    assert LINE_BELOW == 2.5
    box = find_anchor(pdf, AnchorRule(ANCHOR_TEXT))
    assert box is not None and box.page == 2
    out = stamp(pdf, [Stamp(Placement(box.page, box.x, box.y, box.w, box.h), typed_name="Pat Example",
                            caption="Signed electronically by Pat Example")])
    runs = _runs(out, 1)
    caption = next(y for text, y in runs if text.startswith("Signed electronically"))
    assert caption + 0.72 * _CAPTION_SIZE <= line_y - 1  # the caption's glyph top is clear below the ruled line
    assert (1 - box.y - box.h) * PAGE_H + _BAND - line_y < 4 and line_y - ((1 - box.y - box.h) * PAGE_H + _BAND) < 4
    # (the sample has no row under the line, so the next-row condition is vacuous: nothing else is printed below it)
    assert all(y > line_y for text, y in runs if not text.startswith("Signed electronically"))
    label = next(y for text, y in runs if text == ANCHOR_TEXT)
    assert abs(label - LINE_Y) < 0.5
