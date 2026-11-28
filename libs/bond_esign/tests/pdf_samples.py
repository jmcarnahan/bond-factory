"""reportlab-made sample PDFs and a throwaway PNG for the document tests (no network, no files)."""

import io
from dataclasses import dataclass

from PIL import Image
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


@dataclass
class Text:
    x: float
    y: float  # PDF coordinates, origin bottom-left
    text: str
    size: float = 11.0
    split_at: int | None = None  # draw the text as two separate runs, split at this character


def make_pdf(pages: list[list[Text]], size=(612.0, 792.0)) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size, invariant=1)
    for items in pages:
        for t in items:
            c.setFont("Helvetica", t.size)
            if t.split_at is None:
                c.drawString(t.x, t.y, t.text)
            else:
                first, rest = t.text[: t.split_at], t.text[t.split_at :]
                c.drawString(t.x, t.y, first)
                c.drawString(t.x + stringWidth(first, "Helvetica", t.size), t.y, rest)
        c.showPage()
    c.save()
    return buf.getvalue()


def text_width(text: str, size: float = 11.0) -> float:
    return stringWidth(text, "Helvetica", size)


def make_png(width=240, height=80, alpha=True) -> bytes:
    """A transparent canvas with a diagonal stroke (a stand-in for a drawn signature)."""
    img = Image.new("RGBA" if alpha else "RGB", (width, height), (0, 0, 0, 0) if alpha else (255, 255, 255))
    px = img.load()
    for x in range(10, width - 10):
        y = height // 2 + int(20 * ((x % 40) / 40 - 0.5))
        for dy in range(-2, 3):
            px[x, min(max(y + dy, 0), height - 1)] = (10, 20, 120, 255)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()
