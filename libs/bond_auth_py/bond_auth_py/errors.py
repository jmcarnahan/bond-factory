"""Auth refusal codes, default messages and the exception an app maps to its error body.

The library never imports a web framework or the service kit: a route catches ``AuthRefused`` and renders
``exc.detail()`` (``{"code", "message", "hint"?}``) with ``exc.status``.
"""

NOT_INVITED = "not_invited"
IDENTITY_MISMATCH = "identity_mismatch"
DEACTIVATED = "deactivated"
EMAIL_NOT_VERIFIED = "email_not_verified"
INVALID_TOKEN = "invalid_token"
SESSION_REVOKED = "session_revoked"
FIREBASE_NOT_CONFIGURED = "firebase_not_configured"
PROVIDER_NOT_ALLOWED = "provider_not_allowed"
COMPANY_SUSPENDED = "company_suspended"
AUTH_UNAVAILABLE = "auth_unavailable"

#: ``code -> (http status, default message)``.
REFUSALS: dict[str, tuple[int, str]] = {
    NOT_INVITED: (403, "This address was not invited."),
    IDENTITY_MISMATCH: (403, "This sign-in does not match the account linked to this address."),
    DEACTIVATED: (403, "This account is deactivated. Ask the owner."),
    EMAIL_NOT_VERIFIED: (403, "This e-mail address has not been verified."),
    INVALID_TOKEN: (401, "The sign-in could not be verified. Sign in again."),
    SESSION_REVOKED: (401, "This session was ended. Sign in again."),
    FIREBASE_NOT_CONFIGURED: (501, "Firebase sign-in is not configured on this server."),
    PROVIDER_NOT_ALLOWED: (403, "This sign-in method is not allowed for this account."),
    COMPANY_SUSPENDED: (403, "This company is suspended."),
    # A provider outage, not a rejected sign-in: clients must keep the person signed in and retry.
    AUTH_UNAVAILABLE: (503, "Sign-in is temporarily unavailable. Try again shortly."),
}

HINT_APPLE_RELAY = "apple_relay"
#: Apple's "Hide My Email" addresses: a person who hid theirs cannot match an invite.
APPLE_RELAY_SUFFIX = "@privaterelay.appleid.com"


class AuthRefused(Exception):
    """A refused sign-in or session. ``status`` and ``message`` default from the code."""

    def __init__(self, code: str, message: str | None = None, hint: str | None = None,
                 status: int | None = None):
        default_status, default_message = REFUSALS.get(code, (403, code.replace("_", " ")))
        self.code = code
        self.message = message or default_message
        self.hint = hint
        self.status = status or default_status
        super().__init__(f"{code}: {self.message}")

    def detail(self) -> dict:
        body = {"code": self.code, "message": self.message}
        if self.hint:
            body["hint"] = self.hint
        return body


class SessionRevoked(AuthRefused):
    """The session (or the sign-in behind an exchange) predates ``sessions_valid_after``: 401 ``session_revoked``."""

    def __init__(self, message: str | None = None):
        super().__init__(SESSION_REVOKED, message)


class TokenError(Exception):
    """A token that cannot be used. ``reason``: ``malformed``, ``incomplete``, ``expired`` or ``invalid``.
    Routes answer every reason with one 401 ``invalid_token`` so the response never says why."""

    def __init__(self, reason: str = "invalid"):
        self.reason = reason
        super().__init__(reason)


class EmailNotVerified(Exception):
    """A valid token whose e-mail the identity provider has not verified (anyone can register an unverified address)."""


class AuthUnavailable(Exception):
    """Firebase (or the verifier) is not configured or the call failed. Messages never carry a key or token."""


class AuthNotConfigured(AuthUnavailable):
    """Verification is not configured at all (no project id, no verifier): 501 ``firebase_not_configured``.
    Plain ``AuthUnavailable`` is a transport or certificate failure: 503 ``auth_unavailable``."""


class IdentityExists(Exception):
    """An identity with that e-mail already exists."""


class IdentityNotFound(Exception):
    """No identity with that uid or e-mail."""


class MailNotSent(Exception):
    """The set-password mail could not be sent (no web API key, refused, network)."""


def not_invited(email: str) -> AuthRefused:
    """``not_invited``, with the ``apple_relay`` hint when the address is an Apple private relay."""
    hint = HINT_APPLE_RELAY if (email or "").strip().lower().endswith(APPLE_RELAY_SUFFIX) else None
    return AuthRefused(NOT_INVITED, hint=hint)
