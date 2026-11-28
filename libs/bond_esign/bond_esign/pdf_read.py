"""Reading facts from PDF bytes: hash and page count."""

import hashlib
import io

from bond_esign.errors import INVALID_PDF, EsignError


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def visible_box(page) -> tuple[float, float, float, float]:
    """(left, bottom, width, height) of the visible page: its CropBox when it has one, else its MediaBox.

    Stamp placements and anchor results are fractions of this box, so a found anchor stamps where it was found.
    """
    box = page.cropbox  # pypdf falls back to the MediaBox when there is no /CropBox
    return float(box.left), float(box.bottom), float(box.width), float(box.height)


def is_rotated(page) -> bool:
    """True when the page is displayed rotated; pypdf resolves indirect and inherited /Rotate values."""
    return int(page.rotation) % 360 != 0


def page_count(pdf: bytes) -> int:
    """Number of pages; ``invalid_pdf`` when the bytes do not open as a PDF with at least one page."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            raise EsignError(INVALID_PDF, "This PDF is password-protected and cannot be signed.")
        count = len(reader.pages)
    except EsignError:
        raise
    except Exception as exc:  # pypdf raises several unrelated types on bad input
        raise EsignError(INVALID_PDF, "This file is not a readable PDF.") from exc
    if count < 1:
        raise EsignError(INVALID_PDF, "This PDF has no pages.")
    return count
