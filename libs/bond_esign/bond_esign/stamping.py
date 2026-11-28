"""Draw signatures onto the original pages: one reportlab overlay per stamped page, merged with pypdf."""

import io
from collections.abc import Sequence

from bond_esign import _text
from bond_esign.errors import INVALID_PDF, EsignError
from bond_esign.pdf_read import is_rotated, visible_box
from bond_esign.types import Placement, Stamp

_CAPTION_SIZE = 6.5
_DATE_SIZE = 10.0
_MARGIN = 18.0
_BAND = 8.0  # caption band at the bottom of the box


def _box(placement: Placement, x0: float, y0: float, width: float, height: float):
    """(left, bottom, w, h) in PDF points for a top-left fractional placement."""
    left = x0 + placement.x * width
    w = placement.w * width
    h = placement.h * height
    bottom = y0 + height - placement.y * height - h
    return left, bottom, w, h


def _typed(c, name: str, box, font_path: str | None) -> None:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    left, bottom, w, h = box
    font = _text.ttf_name(font_path) if font_path else "Times-Italic"
    text = name if font_path else _text.safe(name)
    size = min(h * 0.75, 28.0)
    while size > 8.0 and stringWidth(text, font, size) > w:
        size -= 0.5
    c.setFillColorRGB(0.05, 0.1, 0.35)
    c.setFont(font, size)
    c.drawString(left, bottom + h * 0.2, text)
    c.setFillColorRGB(0, 0, 0)


def _image(c, png: bytes, box) -> None:
    from reportlab.lib.utils import ImageReader

    left, bottom, w, h = box
    reader = ImageReader(io.BytesIO(png))
    iw, ih = reader.getSize()
    scale = min(w / iw, h / ih)
    c.drawImage(reader, left, bottom, width=iw * scale, height=ih * scale, mask="auto")


def _caption(c, text: str, box, page_right: float, font_path: str | None = None) -> None:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    left, bottom, _, _ = box
    font, text = _text.font_for(text, "Helvetica", font_path)
    room = page_right - _MARGIN - left
    while text and stringWidth(text, font, _CAPTION_SIZE) > room:
        text = text[:-1]
    c.setFont(font, _CAPTION_SIZE)
    c.drawString(left, bottom + 0.5, text)


def _overlay(items: list[Stamp], x0: float, y0: float, width: float, height: float, font_path) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(x0 + width, y0 + height), invariant=1, pageCompression=0)
    c.setTitle("")
    for s in items:
        box = _box(s.placement, x0, y0, width, height)
        band = _BAND if s.caption else 0.0  # the caption takes the bottom of the box; the signature sits above it
        above = (box[0], box[1] + band, box[2], box[3] - band)
        if s.png:
            _image(c, s.png, above)
        elif s.typed_name:
            _text.require_renderable(s.typed_name, font_path)
            _typed(c, s.typed_name, above, font_path)
        if s.caption:
            _caption(c, s.caption, box, x0 + width, font_path)
        if s.date_text and s.date_placement is not None:  # without a box of its own the date is not drawn
            dbox = _box(s.date_placement, x0, y0, width, height)
            c.setFont("Helvetica", _DATE_SIZE)
            c.drawString(dbox[0], dbox[1] + dbox[3] * 0.2, _text.safe(s.date_text))
    c.showPage()
    c.save()
    return buf.getvalue()


def stamp(pdf: bytes, stamps: Sequence[Stamp], *, font_path: str | None = None) -> bytes:
    """Return ``pdf`` with every stamp drawn on its page. Pages with no stamp are not touched.

    A negative ``Placement.page`` counts from the end. A typed name outside cp1252 without ``font_path``
    raises ``name_not_renderable``. A ``date_placement`` is drawn on the same page as the signature box.
    Placement fractions are of the visible page (its CropBox when there is one, else the MediaBox), the same
    box ``find_anchor`` measures. A stamp on a page with /Rotate other than 0 raises ``ValueError``
    ("... rotated pages are not supported") instead of landing in the wrong place.
    """
    from pypdf import PdfReader, PdfWriter

    try:
        reader = PdfReader(io.BytesIO(pdf))
        writer = PdfWriter(clone_from=reader)
    except Exception as exc:
        raise EsignError(INVALID_PDF, "This file is not a readable PDF.") from exc
    total = len(writer.pages)
    by_page: dict[int, list[Stamp]] = {}
    for s in stamps:
        p = s.placement.page
        number = p if p > 0 else total + 1 + p
        if not 1 <= number <= total:
            raise EsignError(INVALID_PDF, f"The document has no page {p}.")
        by_page.setdefault(number, []).append(s)
    for number, items in sorted(by_page.items()):
        page = writer.pages[number - 1]
        if is_rotated(page):
            raise ValueError(f"page {number} has a /Rotate; rotated pages are not supported")
        data = _overlay(items, *visible_box(page), font_path)
        page.merge_page(PdfReader(io.BytesIO(data)).pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
