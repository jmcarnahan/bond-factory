"""bond_esign: electronic signing of a PDF on the app's own page.

A library only: tables (mixins), service functions, a hash-chained evidence log, a signed-PDF builder and a
web panel. Names that need the optional ``seal`` extra (``Sealer``, ``verify_seal``, ``make_self_signed_pkcs12``)
are loaded on first use, so ``import bond_esign`` works without the extra; without it,
``hasattr(bond_esign, "Sealer")`` raises ImportError (not AttributeError). The barrel names ``evidence`` and
``stamp`` are functions, not submodules.
"""

from importlib import import_module

from bond_esign import errors, events
from bond_esign.consent import default_consent
from bond_esign.errors import EsignError
from bond_esign.events import (
    CODE_FAILED,
    CODE_SENT,
    CODE_VERIFIED,
    COMPLETED,
    CONSENT_GIVEN,
    COPY_DELIVERED,
    CREATED,
    DECLINED,
    DOCUMENT_BUILT,
    DOWNLOADED,
    EXPIRED,
    KINDS,
    SIGNED,
    TOKEN_ISSUED,
    VIEWED,
    VOIDED,
    append,
    canonical,
    chain,
    row_hash,
    verify_chain,
)
from bond_esign.labels import CertificateLabels
from bond_esign.models import EsignEventMixin, EsignRequestMixin, EsignSignerMixin, TenantEsignRequestMixin
from bond_esign.pdf_read import page_count, sha256_hex
from bond_esign.service import (
    build_signed_pdf,
    complete,
    create_request,
    decline,
    evidence,
    expire_due,
    find_signer_by_token,
    issue_code,
    issue_token,
    policy_of,
    record_delivery,
    record_download,
    sign,
    signing_view,
    verify_code,
    void,
)
from bond_esign.signature_image import normalise_png, typed_renderable
from bond_esign.types import (
    AnchorRule,
    Brand,
    CertificateData,
    CertificateEvent,
    CertificateSigner,
    ChainCheck,
    Consent,
    EvidenceCheck,
    Placement,
    Policy,
    RequestContext,
    SealCheck,
    SealResult,
    SignedDocument,
    SignerSpec,
    SigningView,
    SignOutcome,
    Stamp,
    Tables,
)
from bond_esign.verify import verify_evidence

__version__ = "0.1.0"

# name -> module that provides it; loaded on first access (PEP 562)
_LAZY = {
    "find_anchor": "anchor",
    "stamp": "stamping",
    "certificate_pages": "certificate",
    "render_panel": "webform",
    "parse_submission": "webform",
    "PanelLabels": "webform",
    "Submission": "webform",
    "asset_path": "webform",
    "asset_names": "webform",
    "asset_tags": "webform",
    "Sealer": "seal",
    "verify_seal": "seal",
    "make_self_signed_pkcs12": "certs",
}

__all__ = [
    "CODE_FAILED",
    "CODE_SENT",
    "CODE_VERIFIED",
    "COMPLETED",
    "CONSENT_GIVEN",
    "COPY_DELIVERED",
    "CREATED",
    "DECLINED",
    "DOCUMENT_BUILT",
    "DOWNLOADED",
    "EXPIRED",
    "KINDS",
    "SIGNED",
    "TOKEN_ISSUED",
    "VIEWED",
    "VOIDED",
    # types
    "AnchorRule",
    "Brand",
    "CertificateData",
    "CertificateEvent",
    "CertificateLabels",
    "CertificateSigner",
    "ChainCheck",
    "Consent",
    # errors
    "EsignError",
    # tables
    "EsignEventMixin",
    "EsignRequestMixin",
    "EsignSignerMixin",
    "EvidenceCheck",
    "PanelLabels",
    "Placement",
    "Policy",
    "RequestContext",
    "SealCheck",
    "SealResult",
    "Sealer",
    "SignOutcome",
    "SignedDocument",
    "SignerSpec",
    "SigningView",
    "Stamp",
    "Submission",
    "Tables",
    "TenantEsignRequestMixin",
    "__version__",
    "append",
    "asset_names",
    "asset_path",
    "asset_tags",
    "build_signed_pdf",
    "canonical",
    "certificate_pages",
    "chain",
    "complete",
    # service
    "create_request",
    "decline",
    "default_consent",
    "errors",
    # events
    "events",
    "evidence",
    "expire_due",
    # loaded on first use
    "find_anchor",
    "find_signer_by_token",
    "issue_code",
    "issue_token",
    "make_self_signed_pkcs12",
    # signature, consent, pdf facts
    "normalise_png",
    "page_count",
    "parse_submission",
    "policy_of",
    "record_delivery",
    "record_download",
    "render_panel",
    "row_hash",
    "sha256_hex",
    "sign",
    "signing_view",
    "stamp",
    "typed_renderable",
    "verify_chain",
    "verify_code",
    "verify_evidence",
    "verify_seal",
    "void",
]


def __getattr__(name: str):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module 'bond_esign' has no attribute {name!r}")
    value = getattr(import_module(f"bond_esign.{module}"), name)
    globals()[name] = value
    return value
