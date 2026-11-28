"""CertificateData builders for tests."""

from datetime import datetime

from pdf_samples import make_png

from bond_esign.types import CertificateData, CertificateEvent, CertificateSigner

HEAD = "ab" * 32


def signer(name="Pat Example", kind="typed", **kw) -> CertificateSigner:
    base = dict(  # noqa: C408
        ref="1a2b3c4d", name=name, email="pat@example.com", role="customer", status="signed", method="link",
        signed_at=datetime(2026, 11, 27, 18, 30, 5), ip="203.0.113.7", user_agent="UA/1.0 " + "x" * 200,
        signature_kind=kind, typed_name=name if kind == "typed" else None,
        signature_png=make_png() if kind == "drawn" else None, signature_sha256="cd" * 32,
    )  # fmt: skip
    base.update(kw)
    return CertificateSigner(**base)


def data(signers=None, events=None, **kw) -> CertificateData:
    base = dict(  # noqa: C408
        request_id="req-0001", title="Sample estimate 100", document_sha256="ef" * 32, page_count=1,
        consent_version="bond-esign-consent/1", consent_language="en", consent_sha256="12" * 32,
        consent_text="I agree to sign this document electronically.",
        signers=tuple(signers if signers is not None else [signer()]),
        events=tuple(
            events
            if events is not None
            else [CertificateEvent(1, datetime(2026, 11, 27, 18, 0, 0), "created"),
                  CertificateEvent(2, datetime(2026, 11, 27, 18, 30, 5), "signed", "Pat Example")]
        ),
        chain_head=HEAD,
    )  # fmt: skip
    base.update(kw)
    return CertificateData(**base)
