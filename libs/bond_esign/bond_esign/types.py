"""Plain values shared by every module of the library. No SQLAlchemy, no PDF library, no I/O."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Placement:
    page: int  # 1-based; negative counts from the end (-1 = last page)
    x: float  # fractions of the page box, origin TOP-LEFT, 0..1
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class AnchorRule:
    text: str  # printed text to find
    occurrence: int = -1  # which match in reading order (0-based); -1 = last
    dx: float = 0.01  # box origin relative to the anchor's right edge / baseline, page fractions
    dy: float = -0.045
    w: float = 0.30
    h: float = 0.0615  # box bottom 13pt below the baseline on Letter: clear of a ruled line 2 to 6pt below it
    case_sensitive: bool = False


@dataclass(frozen=True)
class SignerSpec:
    name: str
    email: str | None = None
    role: str = "signer"
    key: str | None = None  # the app's own reference
    placement: Placement | None = None  # wins over anchor
    anchor: AnchorRule | None = None
    date_placement: Placement | None = None
    date_anchor: AnchorRule | None = None  # used when date_placement is not given


@dataclass(frozen=True)
class RequestContext:
    ip: str | None = None
    user_agent: str | None = None
    actor: str | None = None  # app user id when staff acts or witnesses; None for the signer


@dataclass(frozen=True)
class Consent:
    version: str
    language: str
    text: str


@dataclass(frozen=True)
class Policy:
    require_email_code: bool = False
    allow_typed: bool = True
    allow_drawn: bool = True
    max_signers: int = 10
    max_signature_bytes: int = 200_000
    max_pdf_bytes: int = 25_000_000
    code_ttl_seconds: int = 600
    code_max_attempts: int = 5
    code_resend_seconds: int = 30
    view_event_gap_seconds: int = 3600  # at most one "viewed" event per signer per gap
    typed_charset: str = "latin-1"  # "latin-1" (standard PDF fonts) | "any" (the app passes Brand.font_path)


@dataclass(frozen=True)
class Tables:
    request: type
    signer: type
    event: type


@dataclass(frozen=True)
class Brand:
    name: str | None = None
    logo_png: bytes | None = None
    accent_rgb: tuple[int, int, int] | None = None
    font_path: str | None = None  # a TTF for typed names outside Latin-1


@dataclass(frozen=True)
class Stamp:
    placement: Placement
    png: bytes | None = None
    typed_name: str | None = None
    caption: str | None = None
    date_text: str | None = None
    date_placement: Placement | None = None


@dataclass(frozen=True)
class SigningView:
    request_status: str
    signer_status: str
    can_sign: bool
    reason: str | None  # an error code from errors.py when can_sign is False
    consent: Consent
    needs_code: bool
    code_verified: bool
    allow_typed: bool
    allow_drawn: bool
    signer_name: str
    title: str


@dataclass(frozen=True)
class SignOutcome:
    request: object
    signer: object
    all_signed: bool
    replay: bool


@dataclass(frozen=True)
class SignedDocument:
    pdf: bytes
    sha256: str
    pages: int
    sealed: bool = False
    timestamped: bool = False
    timestamp_url: str | None = None


@dataclass(frozen=True)
class ChainCheck:
    ok: bool
    count: int
    broken_seq: int | None = None


@dataclass(frozen=True)
class SealResult:
    pdf: bytes
    timestamped: bool = False
    timestamp_url: str | None = None


@dataclass(frozen=True)
class EvidenceCheck:
    """The hash chain plus a cross-check of the stored rows against the hashed events."""

    ok: bool
    chain: ChainCheck
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class SealCheck:
    """``intact`` means unmodified since sealing, not who sealed it: compare ``fingerprint`` too."""

    present: bool
    intact: bool = False
    covers_whole_file: bool = False
    subject: str | None = None
    signed_at: datetime | None = None
    timestamped: bool = False
    fingerprint: str | None = None  # sha256 hex of the signer certificate (DER)
    trusted: bool | None = None  # fingerprint == expected_fingerprint; None when none was given


@dataclass(frozen=True)
class CertificateSigner:
    ref: str  # first 8 characters of the signer id
    name: str
    email: str | None
    role: str
    status: str  # pending | signed | declined
    method: str | None = None
    witness: str | None = None
    signed_at: datetime | None = None  # naive UTC
    ip: str | None = None
    user_agent: str | None = None
    signature_kind: str | None = None  # typed | drawn
    typed_name: str | None = None
    signature_png: bytes | None = None
    signature_sha256: str | None = None


@dataclass(frozen=True)
class CertificateEvent:
    seq: int
    at: datetime  # naive UTC
    kind: str
    signer_name: str | None = None
    detail: str | None = None  # e.g. which document a `downloaded` event was about


@dataclass(frozen=True)
class CertificateData:
    request_id: str
    title: str
    document_sha256: str
    page_count: int
    consent_version: str
    consent_language: str
    consent_sha256: str
    consent_text: str
    signers: tuple[CertificateSigner, ...]
    events: tuple[CertificateEvent, ...]
    chain_head: str  # row_hash of the last `signed` event (the last one the certificate lists)
    zone: str = "UTC"  # IANA name for the second, local, time column
