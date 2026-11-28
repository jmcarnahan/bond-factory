"""Compose the signed PDF: stamps, certificate pages, fixed metadata, optional seal. Pure and deterministic."""

import io
from collections.abc import Sequence

from bond_esign.certificate import certificate_pages
from bond_esign.errors import INVALID_PDF, EsignError
from bond_esign.labels import CertificateLabels
from bond_esign.pdf_read import page_count, sha256_hex
from bond_esign.stamping import stamp
from bond_esign.types import Brand, CertificateData, SignedDocument, Stamp


def _assemble(stamped: bytes, cert: bytes, title: str, ident: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, ByteStringObject, NameObject, TextStringObject

    try:
        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(stamped)))
    except Exception as exc:
        raise EsignError(INVALID_PDF, "This file is not a readable PDF.") from exc
    for page in PdfReader(io.BytesIO(cert)).pages:
        writer.add_page(page)
    info = writer._info.get_object() if writer._info is not None else None
    if info is not None:
        for key in list(info.keys()):
            del info[key]
        info[NameObject("/Title")] = TextStringObject(title)
        info[NameObject("/Producer")] = TextStringObject("bond_esign")
    else:
        writer.add_metadata({"/Title": title, "/Producer": "bond_esign"})
    ident16 = ident[:16]
    # pypdf 7 writes the trailer /ID from ``_file_identifiers`` (cloned from the input unless replaced here)
    writer._file_identifiers = ArrayObject([ByteStringObject(ident16), ByteStringObject(ident16)])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def compose(
    pdf: bytes,
    *,
    title: str,
    stamps: Sequence[Stamp],
    certificate: CertificateData,
    labels: CertificateLabels,
    brand: Brand | None = None,
    sealer=None,  # anything with .seal(pdf: bytes) -> SealResult
) -> SignedDocument:
    """Stamp, append the certificate, write with fixed metadata, optionally seal.

    Unsealed output is byte-identical for equal inputs. Sealed output is not (the signature carries a time).
    """
    stamped = stamp(pdf, stamps, font_path=brand.font_path if brand else None) if stamps else pdf
    cert = certificate_pages(certificate, labels=labels, brand=brand)
    ident = bytes.fromhex(
        sha256_hex(pdf + sha256_hex(stamped).encode() + sha256_hex(cert).encode() + title.encode("utf-8"))
    )  # the trailer /ID: the first 16 bytes, twice
    final = _assemble(stamped, cert, title, ident)
    if sealer is None:
        return SignedDocument(pdf=final, sha256=sha256_hex(final), pages=page_count(final))
    result = sealer.seal(final)
    return SignedDocument(
        pdf=result.pdf,
        sha256=sha256_hex(result.pdf),
        pages=page_count(result.pdf),
        sealed=True,
        timestamped=result.timestamped,
        timestamp_url=result.timestamp_url,
    )
