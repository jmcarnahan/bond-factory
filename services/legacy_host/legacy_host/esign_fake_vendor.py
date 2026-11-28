"""An in-memory stand-in for the third-party vendor the app used before bond_esign (no network, ever)."""

from __future__ import annotations

from .esign_seam import CANNOT_VOID, EsignError


class FakeVendorProvider:
    def __init__(self, name: str = "fakevendor") -> None:
        self.name = name
        self.envelopes: dict[str, dict] = {}

    def create_envelope(self, *, estimate, pdf: bytes, file_name: str, signer_name: str, signer_email: str,
                        client_user_id: str, email_subject: str) -> str:
        envelope_id = f"FV-{len(self.envelopes) + 1}"
        self.envelopes[envelope_id] = {"status": "sent", "pdf": pdf, "file_name": file_name,
                                       "signer_email": signer_email, "client_user_id": client_user_id}
        return envelope_id

    def recipient_view_url(self, *, envelope_id: str, signer_name: str, signer_email: str, client_user_id: str,
                           return_url: str) -> str:
        self._get(envelope_id)
        return f"https://vendor.example.com/sign/{envelope_id}?return={return_url}"

    def void(self, envelope_id: str, reason: str) -> None:
        envelope = self._get(envelope_id)
        if envelope["status"] == "completed":
            raise EsignError("Completed envelopes cannot be voided.", code=CANNOT_VOID)
        envelope["status"] = "voided"

    def fetch_signed_pdf(self, envelope_id: str) -> bytes:
        envelope = self._get(envelope_id)
        if envelope["status"] != "completed":
            raise EsignError("The envelope is not completed yet.", retryable=True, code="ENVELOPE_NOT_COMPLETED")
        return envelope["pdf"] + b"\n%vendor-signed"

    def status(self, envelope_id: str) -> str:
        return self._get(envelope_id)["status"]

    def remember(self, envelope_id: str, status: str, pdf: bytes = b"%PDF-1.4 old") -> None:
        """An envelope the vendor already had before this process started (the app's old rows)."""
        self.envelopes[envelope_id] = {"status": status, "pdf": pdf}

    def set_status(self, envelope_id: str, status: str) -> None:
        """What the vendor's webhook would do (test helper)."""
        self._get(envelope_id)["status"] = status

    def _get(self, envelope_id: str) -> dict:
        try:
            return self.envelopes[envelope_id]
        except KeyError:
            raise EsignError(f"unknown envelope {envelope_id}", code="ENVELOPE_NOT_FOUND") from None
