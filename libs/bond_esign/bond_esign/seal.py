"""Seal a finished PDF (PAdES, one invisible signature over the whole file) and check a seal later.

``Sealer.seal`` uses pyHanko's synchronous API: call it from sync code (a job worker), not from inside a
running event loop. Sealed output is not byte-deterministic (the signature carries a time).
"""

import hashlib
import hmac
import io
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

try:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign import fields, signers, timestamps
    from pyhanko.sign.fields import SigFieldSpec
    from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata, PdfSigner
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko.sign.validation.status import SignatureCoverageLevel
    from pyhanko_certvalidator import ValidationContext
except ImportError as exc:  # pragma: no cover
    raise ImportError("bond_esign.seal needs the 'seal' extra: install bond_esign[seal]") from exc

from bond_esign.errors import SEAL_FAILED, EsignError
from bond_esign.types import SealCheck, SealResult


def _naive_utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment


class Sealer:
    def __init__(
        self,
        signer: Any,
        *,
        timestamp_urls: Sequence[str] = (),
        require_timestamp: bool = False,
        field_name: str = "BondEsignSeal",
        reason: str | None = None,
        location: str | None = None,
        timestamper_factory: Callable[[str], Any] | None = None,
    ):
        self._signer = signer
        self.timestamp_urls = tuple(timestamp_urls)
        self.require_timestamp = require_timestamp
        self.field_name = field_name
        self.reason = reason
        self.location = location
        self._factory = timestamper_factory or (lambda url: timestamps.HTTPTimeStamper(url))

    @classmethod
    def from_pkcs12(
        cls,
        data: bytes,
        passphrase: bytes | None,
        *,
        timestamp_urls: Sequence[str] = (),
        require_timestamp: bool = False,
        field_name: str = "BondEsignSeal",
        reason: str | None = None,
        location: str | None = None,
        timestamper_factory: Callable[[str], Any] | None = None,
    ) -> "Sealer":
        try:
            signer = signers.SimpleSigner.load_pkcs12_data(data, other_certs=[], passphrase=passphrase)
        except Exception as exc:
            raise EsignError(SEAL_FAILED, "The sealing certificate could not be opened.") from exc
        if signer is None:
            raise EsignError(SEAL_FAILED, "The sealing certificate could not be opened.")
        return cls(
            signer, timestamp_urls=timestamp_urls, require_timestamp=require_timestamp, field_name=field_name,
            reason=reason, location=location, timestamper_factory=timestamper_factory,
        )  # fmt: skip

    @property
    def fingerprint(self) -> str:
        """sha256 hex of this sealer's certificate (DER): store it, then pass it as ``expected_fingerprint``."""
        return hashlib.sha256(self._signer.signing_cert.dump()).hexdigest()

    def _sign_once(self, pdf: bytes, timestamper) -> bytes:
        meta = PdfSignatureMetadata(
            field_name=self.field_name, md_algorithm="sha256", subfilter=fields.SigSeedSubFilter.PADES,
            reason=self.reason, location=self.location,
        )  # fmt: skip
        signer = PdfSigner(
            meta, signer=self._signer, timestamper=timestamper, new_field_spec=SigFieldSpec(self.field_name)
        )
        out = io.BytesIO()
        signer.sign_pdf(IncrementalPdfFileWriter(io.BytesIO(pdf)), output=out)
        return out.getvalue()

    def seal(self, pdf: bytes) -> SealResult:
        """Sign ``pdf``. Timestamp servers are tried in order; if all fail, seal without one unless required."""
        try:
            for url in self.timestamp_urls:
                try:
                    return SealResult(self._sign_once(pdf, self._factory(url)), True, url)
                except Exception:  # noqa: BLE001, S112  unreachable or refusing server: try the next
                    continue
            if self.timestamp_urls and self.require_timestamp:
                raise EsignError(SEAL_FAILED, "No timestamp server answered, so the document was not sealed.")
            if self.require_timestamp and not self.timestamp_urls:
                raise EsignError(SEAL_FAILED, "A timestamp is required but no timestamp server is configured.")
            return SealResult(self._sign_once(pdf, None), False, None)
        except EsignError:
            raise
        except Exception as exc:  # pyHanko raises many types
            raise EsignError(SEAL_FAILED, "The document could not be sealed.") from exc


def verify_seal(pdf: bytes, *, expected_fingerprint: str | None = None) -> SealCheck:
    """Report on the first embedded signature. Needs no trust and touches no network.

    ``intact`` means unmodified since sealing, not who sealed it: compare ``fingerprint`` (or pass
    ``expected_fingerprint`` to get ``trusted``), and compare the file's sha256 with ``request.signed_sha256``.
    """
    try:
        sigs = PdfFileReader(io.BytesIO(pdf)).embedded_signatures
    except Exception:  # noqa: BLE001  not a PDF pyHanko can read: no seal to report
        return SealCheck(present=False)
    if not sigs:
        return SealCheck(present=False)
    sig = sigs[0]
    try:
        fingerprint = hashlib.sha256(sig.signer_cert.dump()).hexdigest()
    except Exception:  # noqa: BLE001
        fingerprint = None
    trusted = None
    if expected_fingerprint is not None:
        trusted = fingerprint is not None and hmac.compare_digest(
            fingerprint.encode(), expected_fingerprint.strip().lower().encode()
        )
    try:
        # Trust is not judged here (a self-signed seal is fine): the signer's own certificate is the only root,
        # which keeps pyHanko from logging an untrusted-chain error and from reading the OS trust list.
        context = ValidationContext(trust_roots=[sig.signer_cert], allow_fetching=False)
        status = validate_pdf_signature(sig, signer_validation_context=context, skip_diff=True)
    except Exception:  # noqa: BLE001  a seal that cannot be validated is not intact
        return SealCheck(present=True, fingerprint=fingerprint, trusted=trusted)
    ts = status.timestamp_validity
    timestamped = ts is not None and ts.intact and ts.valid
    moment = ts.timestamp if timestamped else status.signer_reported_dt
    try:
        subject = status.signing_cert.subject.native.get("common_name")
    except Exception:  # noqa: BLE001  an odd certificate name is not worth failing for
        subject = None
    return SealCheck(
        present=True,
        intact=bool(status.intact and status.valid),
        covers_whole_file=status.coverage == SignatureCoverageLevel.ENTIRE_FILE,
        subject=subject if isinstance(subject, str) else None,
        signed_at=_naive_utc(moment),
        timestamped=bool(timestamped),
        fingerprint=fingerprint,
        trusted=trusted,
    )
