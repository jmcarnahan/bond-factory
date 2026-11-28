"""Text helpers shared by the stamp and the certificate: safe for the standard PDF fonts, or a TTF."""

from bond_esign.errors import NAME_NOT_RENDERABLE, EsignError
from bond_esign.pdf_read import sha256_hex

_registered: set[str] = set()


def safe(text: str | None) -> str:
    """Replace what the standard fonts (cp1252) cannot draw with '?'; control characters become spaces."""
    out = []
    for ch in text or "":
        if ch in "\r\n\t":
            out.append(" ")
            continue
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


def renderable(text: str) -> bool:
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def ttf_name(font_path: str) -> str:
    """Register the TTF once under a name derived from its path; return that name."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    name = "BondEsignTTF" + sha256_hex(font_path.encode())[:8]
    if name not in _registered:
        pdfmetrics.registerFont(TTFont(name, font_path))
        _registered.add(name)
    return name


def require_renderable(name: str, font_path: str | None) -> None:
    if font_path is None and not renderable(name):
        raise EsignError(
            NAME_NOT_RENDERABLE,
            "This name has characters that cannot be typed as a signature. Please draw your signature instead.",
        )
