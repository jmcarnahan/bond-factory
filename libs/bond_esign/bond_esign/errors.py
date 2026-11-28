"""The one exception the library raises on purpose. ``message`` is plain English, fit to show a signer."""

NOT_OPEN = "not_open"
EXPIRED = "expired"
ALREADY_COMPLETED = "already_completed"
CONSENT_REQUIRED = "consent_required"
CONSENT_STALE = "consent_stale"
CODE_REQUIRED = "code_required"
CODE_INVALID = "code_invalid"
CODE_TOO_SOON = "code_too_soon"
TOO_MANY_ATTEMPTS = "too_many_attempts"
SIGNATURE_REQUIRED = "signature_required"
SIGNATURE_INVALID = "signature_invalid"
TYPED_NOT_ALLOWED = "typed_not_allowed"
DRAWN_NOT_ALLOWED = "drawn_not_allowed"
NAME_NOT_RENDERABLE = "name_not_renderable"
IN_PERSON_NEEDS_ACTOR = "in_person_needs_actor"
DOCUMENT_MISMATCH = "document_mismatch"
INVALID_PDF = "invalid_pdf"
TOO_MANY_SIGNERS = "too_many_signers"
NOT_READY = "not_ready"
HASH_CONFLICT = "hash_conflict"
SEAL_FAILED = "seal_failed"
EVIDENCE_MISMATCH = "evidence_mismatch"

CODES = (
    NOT_OPEN, EXPIRED, ALREADY_COMPLETED, CONSENT_REQUIRED, CONSENT_STALE, CODE_REQUIRED, CODE_INVALID,
    CODE_TOO_SOON, TOO_MANY_ATTEMPTS, SIGNATURE_REQUIRED, SIGNATURE_INVALID, TYPED_NOT_ALLOWED,
    DRAWN_NOT_ALLOWED, NAME_NOT_RENDERABLE, IN_PERSON_NEEDS_ACTOR, DOCUMENT_MISMATCH, INVALID_PDF,
    TOO_MANY_SIGNERS, NOT_READY, HASH_CONFLICT, SEAL_FAILED,
    EVIDENCE_MISMATCH,
)  # fmt: skip


class EsignError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
