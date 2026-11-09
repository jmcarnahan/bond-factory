"""Exceptions. Codes are stable strings an app can map to its own error body."""

from __future__ import annotations


class OAuthError(Exception):
    """A flow failed for a reason the person can fix by starting again.

    ``code`` is one of ``expired_state``, ``invalid_state``, ``provider_mismatch``, ``unknown_provider``,
    ``no_refresh_token``, ``no_email``, ``invalid_code`` or the provider's own error string.
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code.replace("_", " "))
        self.code = code


class ProviderError(OAuthError):
    """The provider answered a token call with an error (``status`` is the HTTP status)."""

    def __init__(self, code: str, status: int, message: str | None = None) -> None:
        super().__init__(code, message)
        self.status = status


class RetryableError(Exception):
    """A timeout, a transport failure or a provider 5xx. The saved connection is fine; try again later."""


class ReconnectRequired(Exception):
    """The provider no longer honours the saved sign-in (or it was revoked): only the person reconnecting helps."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"reconnect required: {reason}")
        self.reason = reason
