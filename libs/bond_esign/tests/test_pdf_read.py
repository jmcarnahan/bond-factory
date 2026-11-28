import hashlib
import io

import pytest
from pdf_samples import Text, make_pdf

from bond_esign.errors import INVALID_PDF, EsignError
from bond_esign.pdf_read import page_count, sha256_hex


def test_sha256_hex():
    assert sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_page_count():
    assert page_count(make_pdf([[Text(50, 50, "a")], [Text(50, 50, "b")]])) == 2


@pytest.mark.parametrize("bad", [b"", b"not a pdf at all", b"%PDF-1.4\ngarbage"])
def test_garbage_is_invalid_pdf(bad):
    with pytest.raises(EsignError) as err:
        page_count(bad)
    assert err.value.code == INVALID_PDF


def _with_indirect_rotate(value: int) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, NumberObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf([[Text(72, 300, "Accepted by (customer)")]]))))
    writer.pages[0][NameObject("/Rotate")] = writer._add_object(NumberObject(value))
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_indirect_rotate_90_is_skipped_and_refused():
    from bond_esign.anchor import AnchorRule, find_anchor
    from bond_esign.stamping import stamp
    from bond_esign.types import Placement, Stamp

    pdf = _with_indirect_rotate(90)
    assert find_anchor(pdf, AnchorRule("Accepted by (customer)")) is None
    with pytest.raises(ValueError, match="rotated pages are not supported"):
        stamp(pdf, [Stamp(Placement(1, 0.3, 0.4, 0.3, 0.055), typed_name="Pat Example")])


def test_indirect_rotate_0_stamps_normally():
    from bond_esign.anchor import AnchorRule, find_anchor
    from bond_esign.stamping import stamp
    from bond_esign.types import Placement, Stamp

    pdf = _with_indirect_rotate(0)
    assert find_anchor(pdf, AnchorRule("Accepted by (customer)")) is not None
    assert stamp(pdf, [Stamp(Placement(1, 0.3, 0.4, 0.3, 0.055), typed_name="Pat Example")])
