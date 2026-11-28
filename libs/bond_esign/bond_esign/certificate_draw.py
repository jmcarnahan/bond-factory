"""A tiny top-to-bottom layout helper for the certificate pages (plain canvas, no markup interpretation)."""

import io

from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from bond_esign import _text

PAGE_W, PAGE_H = 612.0, 792.0
MARGIN = 54.0
TOP = PAGE_H - 54.0
BOTTOM = 62.0
WIDTH = PAGE_W - 2 * MARGIN
GREY = (0.35, 0.38, 0.42)
FIELD_MAX = 300  # characters of any field value printed on the certificate (the consent text is exempt)
IMAGE_GAP = 5.0  # points of clear space above and below an image (at least 4)


def label_names(labels) -> list[str]:
    """Every field label the certificate prints in its header and signer blocks."""
    return [
        labels.document, labels.request_id, labels.document_sha256, labels.pages, labels.email, labels.role,
        labels.method, labels.witness, labels.signed_at, labels.ip, labels.user_agent, labels.consent,
        labels.consent_sha256, labels.signature, labels.signature_sha256,
    ]  # fmt: skip


def value_offset(labels, size: float = 9.0) -> float:
    """x offset (from the field's left edge) where values start: after the widest printed label plus a gap."""
    return max(stringWidth(_text.safe(n), "Helvetica", size) for n in label_names(labels)) + 10.0


def _fit(prefix: str, word: str, font: str, size: float, width: float) -> int:
    """How many leading characters of ``word`` fit after ``prefix`` (binary search; at least 1)."""
    hi = min(len(word), int(width / (size * 0.2)) + 2)  # no character is narrower than a fifth of an em
    lo = 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if stringWidth(prefix + word[:mid], font, size) <= width:
            lo = mid
        else:
            hi = mid - 1
    return lo


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Greedy word wrap that also breaks a single over-long token (cost grows linearly with the text)."""
    lines: list[str] = []
    for para in (text or "").split("\n"):
        cur = ""
        for word in para.split(" "):
            while len(word) > 1 and stringWidth(word[: int(width / (size * 0.2)) + 2], font, size) > width:
                room = cur + (" " if cur else "")
                cut = _fit(room, word, font, size, width)
                if cur and stringWidth(room + word[:cut], font, size) > width:  # nothing fits beside cur
                    lines.append(cur)
                    cur = ""
                    continue
                lines.append(room + word[:cut])
                cur, word = "", word[cut:]
            trial = (cur + " " + word) if cur else word
            if stringWidth(trial, font, size) <= width:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


class Flow:
    def __init__(self, labels, brand, total: int | None):
        self.labels, self.brand, self.total = labels, brand, total
        self.lw = value_offset(labels)
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=(PAGE_W, PAGE_H), invariant=1, pageCompression=0)
        self.c.setTitle("")
        self.page = 1
        self.y = TOP
        self.accent = tuple(v / 255 for v in brand.accent_rgb) if brand and brand.accent_rgb else (0.1, 0.2, 0.4)
        self.name_font = _text.ttf_name(brand.font_path) if brand and brand.font_path else None

    # text for names may use the app's TTF; everything else is cp1252-safe
    def text(self, value, name: bool = False) -> str:
        return value or "" if (name and self.name_font) else _text.safe(value)

    def font(self, bold: bool = False, name: bool = False) -> str:
        if name and self.name_font:
            return self.name_font
        return "Helvetica-Bold" if bold else "Helvetica"

    def ensure(self, height: float) -> None:
        if self.y - height < BOTTOM:
            self.new_page()

    def new_page(self) -> None:
        self._footer()
        self.c.showPage()
        self.page += 1
        self.y = TOP

    def _footer(self) -> None:
        total = self.total or self.page
        self.c.setFillColorRGB(*GREY)
        self.c.setFont("Helvetica", 8)
        self.c.drawRightString(PAGE_W - MARGIN, 36, self.labels.page_of.format(n=self.page, m=total))
        self.c.setFillColorRGB(0, 0, 0)

    def finish(self) -> tuple[bytes, int]:
        self._footer()
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue(), self.page

    def gap(self, h: float) -> None:
        self.y -= h

    def rule(self, color=None) -> None:
        self.ensure(6)
        self.c.setStrokeColorRGB(*(color or (0.8, 0.83, 0.86)))
        self.c.line(MARGIN, self.y, PAGE_W - MARGIN, self.y)
        self.y -= 6

    def heading(self, text: str, size: float = 12) -> None:
        self.ensure(size + 14)
        self.y -= size
        self.c.setFillColorRGB(*self.accent)
        self.c.setFont("Helvetica-Bold", size)
        self.c.drawString(MARGIN, self.y, self.text(text))
        self.c.setFillColorRGB(0, 0, 0)
        self.y -= 6

    def lines(self, text, font="Helvetica", size=9.0, indent=0.0, color=None, name=False, limit=FIELD_MAX) -> None:
        leading = size + 3
        if limit is not None:
            text = (text or "")[:limit]
        for line in wrap(self.text(text, name), font, size, WIDTH - indent):
            self.ensure(leading)
            self.y -= leading
            self.c.setFillColorRGB(*(color or (0, 0, 0)))
            self.c.setFont(font, size)
            self.c.drawString(MARGIN + indent, self.y, line)
        self.c.setFillColorRGB(0, 0, 0)

    def field(self, label: str, value, *, mono=False, name=False, indent=0.0) -> None:
        if value is None or value == "":
            return
        lw = self.lw
        value = str(value)[:FIELD_MAX]
        font = "Courier" if mono else self.font(name=name)
        size = 8.0 if mono else 9.0
        if mono:  # a hash stays on one line: shrink it (floor 5.5pt) rather than wrap it
            room = WIDTH - indent - lw
            while size > 5.5 and stringWidth(str(value), font, size) > room:
                size -= 0.25
        body = wrap(self.text(str(value), name), font, size, WIDTH - indent - lw)
        for i, line in enumerate(body):
            self.ensure(size + 3)
            self.y -= size + 3
            if i == 0:
                self.c.setFillColorRGB(*GREY)
                self.c.setFont("Helvetica", 9)
                self.c.drawString(MARGIN + indent, self.y, self.text(label))
                self.c.setFillColorRGB(0, 0, 0)
            self.c.setFont(font, size)
            self.c.drawString(MARGIN + indent + lw, self.y, line)

    def image(self, png: bytes, max_w: float, max_h: float, indent: float = 0.0) -> None:
        reader = ImageReader(io.BytesIO(png))
        iw, ih = reader.getSize()
        scale = min(max_w / iw, max_h / ih)
        w, h = iw * scale, ih * scale
        self.ensure(h + 2 * IMAGE_GAP)
        self.y -= IMAGE_GAP  # clear space above, so the image never touches the line before it
        self.y -= h
        self.c.drawImage(reader, MARGIN + indent, self.y, width=w, height=h, mask="auto")
        self.y -= IMAGE_GAP  # and below

    def row(self, cells: list[tuple[float, str]], font="Helvetica", size=8.5, grey=False) -> None:
        self.ensure(size + 4)
        self.y -= size + 3
        self.c.setFont(font, size)
        if grey:
            self.c.setFillColorRGB(*GREY)
        for cell in cells:  # (x, value) or (x, value, font_path_for_names)
            x, value = cell[0], cell[1]
            if len(cell) > 2 and cell[2]:  # a name: the TTF only when the standard fonts cannot draw it
                font_here, shown = _text.font_for(value or "", font, cell[2])
                self.c.setFont(font_here, size)
                self.c.drawString(MARGIN + x, self.y, shown)
                self.c.setFont(font, size)
                continue
            self.c.drawString(MARGIN + x, self.y, self.text(value))
        self.c.setFillColorRGB(0, 0, 0)
