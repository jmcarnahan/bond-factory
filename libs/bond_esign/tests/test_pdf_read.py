import hashlib

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
