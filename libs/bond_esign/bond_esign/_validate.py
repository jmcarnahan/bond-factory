"""Programming-error checks on what the app passes to ``create_request`` (``ValueError``, not ``EsignError``)."""

from bond_esign._rows import clean
from bond_esign.types import Consent, Policy

_POSITIVE = ("max_signers", "max_signature_bytes", "max_pdf_bytes", "code_ttl_seconds", "code_max_attempts")
_NOT_NEGATIVE = ("code_resend_seconds", "view_event_gap_seconds")


def check_policy(policy: Policy) -> None:
    if not (policy.allow_typed or policy.allow_drawn):
        raise ValueError("policy: allow_typed and allow_drawn are both False, so nobody could sign")
    for name in _POSITIVE:
        if not getattr(policy, name) > 0:
            raise ValueError(f"policy.{name} must be greater than 0, got {getattr(policy, name)!r}")
    for name in _NOT_NEGATIVE:
        if getattr(policy, name) < 0:
            raise ValueError(f"policy.{name} must not be negative, got {getattr(policy, name)!r}")
    if policy.typed_charset not in ("latin-1", "any"):
        raise ValueError(f"policy.typed_charset must be 'latin-1' or 'any', got {policy.typed_charset!r}")


def _blank(text) -> bool:
    return not (clean(text, 1_000_000) or "").strip()


def check_request(*, title: str, consent: Consent, signers, policy: Policy, expires_at, now) -> None:
    check_policy(policy)
    if _blank(title):
        raise ValueError("title must not be blank")
    if _blank(consent.version) or _blank(consent.text):
        raise ValueError("consent.version and consent.text must not be blank")
    for position, spec in enumerate(signers):
        if _blank(spec.name):
            raise ValueError(f"signer {position} has a blank name")
    if expires_at is not None and expires_at <= now:
        raise ValueError("expires_at must be after now")
