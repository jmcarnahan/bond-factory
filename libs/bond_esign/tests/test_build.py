import hashlib
import io
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from cert_samples import data
from pdf_samples import Text, make_pdf, make_png
from pypdf import PdfReader

from bond_esign.build import compose
from bond_esign.labels import CertificateLabels
from bond_esign.types import Placement, SealResult, Stamp

PDF = make_pdf([[Text(72, 700, "Original page one")], [Text(72, 700, "Original page two")]])
STAMPS = [Stamp(Placement(2, 0.3, 0.4, 0.3, 0.055), png=make_png(), caption="Signed electronically by Pat")]
LABELS = CertificateLabels()


def _compose(**kw):
    return compose(PDF, title="Sample estimate 100", stamps=STAMPS, certificate=data(), labels=LABELS, **kw)


def test_pages_text_and_metadata():
    doc = _compose()
    reader = PdfReader(io.BytesIO(doc.pdf))
    assert doc.pages == 3 == len(reader.pages)
    assert doc.sha256 == hashlib.sha256(doc.pdf).hexdigest()
    assert (doc.sealed, doc.timestamped, doc.timestamp_url) == (False, False, None)
    assert "Original page one" in reader.pages[0].extract_text()
    assert "Signature certificate" in reader.pages[2].extract_text()
    assert len(reader.pages[1].images) == 1
    meta = dict(reader.metadata)
    assert meta["/Title"] == "Sample estimate 100" and meta["/Producer"] == "bond_esign"
    assert "/CreationDate" not in meta and "/ModDate" not in meta


def test_no_stamps_is_certificate_only():
    doc = compose(PDF, title="t", stamps=[], certificate=data(), labels=LABELS)
    assert doc.pages == 3


def test_equal_inputs_give_identical_bytes_in_process():
    assert _compose().pdf == _compose().pdf
    assert _compose().pdf != compose(PDF, title="Other", stamps=STAMPS, certificate=data(), labels=LABELS).pdf


def _trailer_id(pdf: bytes) -> tuple[bytes, bytes]:
    ids = PdfReader(io.BytesIO(pdf)).trailer["/ID"]
    return tuple(getattr(i, "original_bytes", None) or bytes(i) for i in ids)


def test_trailer_id_is_derived_from_the_composed_inputs():
    from bond_esign.certificate import certificate_pages
    from bond_esign.stamping import stamp

    stamped = stamp(PDF, STAMPS)
    cert = certificate_pages(data(), labels=LABELS)
    parts = PDF + hashlib.sha256(stamped).hexdigest().encode() + hashlib.sha256(cert).hexdigest().encode()
    expected = hashlib.sha256(parts + b"Sample estimate 100").digest()[:16]
    assert _trailer_id(_compose().pdf) == (expected, expected)


def test_different_inputs_give_different_trailer_ids():
    base = _trailer_id(_compose().pdf)
    other_title = _trailer_id(compose(PDF, title="Other", stamps=STAMPS, certificate=data(), labels=LABELS).pdf)
    other_pdf = _trailer_id(compose(
        make_pdf([[Text(72, 700, "Different")]]), title="Sample estimate 100", stamps=[], certificate=data(), labels=LABELS
    ).pdf)
    assert len({base, other_title, other_pdf}) == 3
    assert base == _trailer_id(_compose().pdf)


def test_original_metadata_dates_are_dropped():
    from pypdf import PdfWriter

    w = PdfWriter(clone_from=PdfReader(io.BytesIO(PDF)))
    w.add_metadata({"/CreationDate": "D:20200101000000Z", "/Author": "Someone"})
    buf = io.BytesIO()
    w.write(buf)
    out = compose(buf.getvalue(), title="t", stamps=[], certificate=data(), labels=LABELS)
    meta = dict(PdfReader(io.BytesIO(out.pdf)).metadata)
    assert "/CreationDate" not in meta and "/Author" not in meta


def test_sealer_result_is_used():
    class Fake:
        def seal(self, pdf):
            return SealResult(pdf + b"\n%sealed\n", True, "https://tsa.example.com")

    doc = _compose(sealer=Fake())
    assert doc.sealed and doc.timestamped and doc.timestamp_url == "https://tsa.example.com"
    assert doc.pdf.endswith(b"%sealed\n") and doc.sha256 == hashlib.sha256(doc.pdf).hexdigest()


SCRIPT = textwrap.dedent(
    """
    import hashlib, sys
    sys.path.insert(0, sys.argv[1])
    from cert_samples import data
    from pdf_samples import Text, make_pdf, make_png
    from bond_esign.build import compose
    from bond_esign.labels import CertificateLabels
    from bond_esign.types import Placement, Stamp
    pdf = make_pdf([[Text(72, 700, "Original page one")], [Text(72, 700, "Original page two")]])
    stamps = [Stamp(Placement(2, 0.3, 0.4, 0.3, 0.055), png=make_png(), caption="Signed electronically by Pat")]
    out = compose(pdf, title="Sample estimate 100", stamps=stamps, certificate=data(), labels=CertificateLabels())
    print(hashlib.sha256(out.pdf).hexdigest())
    """
)


def test_identical_across_separate_processes(tmp_path):
    here = str(Path(__file__).parent)
    hashes = []
    for seed in ("1", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        run = subprocess.run(
            [sys.executable, "-c", SCRIPT, here], capture_output=True, text=True, check=True, env=env, cwd=tmp_path
        )
        hashes.append(run.stdout.strip())
    assert hashes[0] == hashes[1] and len(hashes[0]) == 64
    assert hashes[0] == hashlib.sha256(_compose().pdf).hexdigest()


def test_garbage_input_is_invalid_pdf():
    from bond_esign.errors import EsignError

    with pytest.raises(EsignError):
        compose(b"nope", title="t", stamps=[], certificate=data(), labels=LABELS)
