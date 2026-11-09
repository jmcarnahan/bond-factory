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
# Refresh sessions (401): every one means "sign in again".
REFRESH_REUSED = "refresh_reused"
REFRESH_EXPIRED = "refresh_expired"
REFRESH_REVOKED = "refresh_revoked"
# Direct sign-in refusals. bond_signin maps codes to statuses from REFUSALS (the one home for strings and statuses).
TENANT_MISMATCH = "tenant_mismatch"
CONSENT_DECLINED = "consent_declined"
SIGNIN_EXPIRED = "signin_expired"
ACCOUNT_MISMATCH = "account_mismatch"
INVALID_ORIGIN = "invalid_origin"
# The rest of the sign-in codes bond_signin answers with (it keeps no status table of its own).
INVALID_REQUEST = "invalid_request"
INVALID_STATE = "invalid_state"
INVALID_HANDOFF = "invalid_handoff"
UNKNOWN_PROVIDER = "unknown_provider"
INVALID_CODE = "invalid_code"
INVALID_ID_TOKEN = "invalid_id_token"
PROVIDER_ERROR = "provider_error"

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
    REFRESH_REUSED: (401, "This session was ended for your security. Sign in again."),
    REFRESH_EXPIRED: (401, "Your session expired. Sign in again."),
    REFRESH_REVOKED: (401, "This session was ended. Sign in again."),
    TENANT_MISMATCH: (403, "This account does not belong to the organization this app is set up for."),
    CONSENT_DECLINED: (403, "Sign-in needs the requested permissions. Start again and allow them."),
    SIGNIN_EXPIRED: (400, "This sign-in took too long or was already used. Start again."),
    ACCOUNT_MISMATCH: (403, "This is not the account you signed in with. Use the same account."),
    INVALID_ORIGIN: (403, "This request came from a page that is not allowed."),
    INVALID_REQUEST: (400, "The request was not valid."),
    INVALID_STATE: (400, "This sign-in could not be matched to this browser or device. Start again."),
    INVALID_HANDOFF: (401, "This sign-in hand-off is invalid or already used. Start again."),
    UNKNOWN_PROVIDER: (404, "That sign-in provider is not available."),
    INVALID_CODE: (400, "The sign-in code was not accepted. Start again."),
    INVALID_ID_TOKEN: (400, "The identity token from the provider could not be verified."),
    PROVIDER_ERROR: (502, "The sign-in provider did not answer correctly. Try again shortly."),
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


class ReuseDetected(AuthRefused):
    """A rotated refresh token was replayed outside the grace window: the whole family is revoked.
    401 ``refresh_reused``. ``rotate`` commits the revocation before raising this."""

    def __init__(self, message: str | None = None):
        super().__init__(REFRESH_REUSED, message)


class RefreshExpired(AuthRefused):
    """The refresh token passed its sliding expiry or the family's absolute cap: 401 ``refresh_expired``."""

    def __init__(self, message: str | None = None):
        super().__init__(REFRESH_EXPIRED, message)


class RefreshRevoked(AuthRefused):
    """Unknown, malformed, revoked or invalidated refresh token: 401 ``refresh_revoked`` (never says which)."""

    def __init__(self, message: str | None = None):
        super().__init__(REFRESH_REVOKED, message)


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
