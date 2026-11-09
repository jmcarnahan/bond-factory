"""Codes, their HTTP status and English default messages. The lib never imports a sibling lib's exception classes.

Any exception that carries a ``str`` attribute ``code`` is understood (``refusal_code``). Unknown codes answer 500 and
only the code is logged.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

LOGGER = logging.getLogger("bond_signin")

STATUS_FOR_CODE: dict[str, int] = {
    # refusals: the person is known but not allowed
    "tenant_mismatch": 403, "email_not_verified": 403, "not_invited": 403, "company_suspended": 403,
    "provider_not_allowed": 403, "deactivated": 403, "identity_mismatch": 403, "consent_declined": 403,
    "account_mismatch": 403, "invalid_origin": 403,
    # a session, hand-off or refresh token that is no longer good
    "session_revoked": 401, "invalid_handoff": 401, "invalid_token": 401,
    "refresh_reused": 401, "refresh_expired": 401, "refresh_revoked": 401,
    # a request or state that is not usable
    "invalid_state": 400, "invalid_request": 400, "signin_expired": 400, "invalid_id_token": 400,
    "not_found": 404, "unknown_provider": 404, "invalid_code": 400, "provider_error": 502,
}

MESSAGES: dict[str, str] = {
    "tenant_mismatch": "This account does not belong to the organization this app is set up for.",
    "email_not_verified": "This e-mail address has not been verified.",
    "not_invited": "This address was not invited.",
    "company_suspended": "This company is suspended.",
    "provider_not_allowed": "This sign-in method is not allowed for this account.",
    "deactivated": "This account is deactivated. Ask the owner.",
    "identity_mismatch": "This sign-in does not match the account linked to this address.",
    "consent_declined": "Sign-in needs the requested permissions. Start again and allow them.",
    "account_mismatch": "This is not the account you signed in with. Use the same account.",
    "invalid_origin": "This request came from a page that is not allowed.",
    "session_revoked": "This session was ended. Sign in again.",
    "invalid_handoff": "This sign-in hand-off is invalid or already used. Start again.",
    "invalid_token": "The sign-in could not be verified. Sign in again.",
    "refresh_reused": "This session was ended for your security. Sign in again.",
    "refresh_expired": "Your session expired. Sign in again.",
    "refresh_revoked": "This session was ended. Sign in again.",
    "invalid_state": "This sign-in could not be matched to this browser or device. Start again.",
    "invalid_request": "The request was not valid.",
    "signin_expired": "This sign-in took too long or was already used. Start again.",
    "invalid_id_token": "The identity token from the provider could not be verified.",
    "not_found": "Not found.",
    "provider_error": "The sign-in provider did not answer correctly. Try again shortly.",
    "invalid_code": "The sign-in code was not accepted. Start again.",
    "unknown_provider": "That sign-in provider is not available.",
    "internal_error": "Something went wrong on our side.",
}


class SignInRefused(Exception):
    """A refusal raised by this lib itself. Carries ``code`` like the sibling libs' exceptions do."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or MESSAGES.get(code, code))
        self.code = code
        self.message = message or MESSAGES.get(code, code)


def refusal_code(exc: BaseException) -> str | None:
    """The ``code`` of an exception that has a non-empty ``str`` attribute ``code``, else None."""
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else None


def http_error(code: str, message: str | None = None) -> HTTPException:
    """``HTTPException`` with ``detail={"code", "message"}`` and the status of ``code`` (500 when unknown)."""
    status = STATUS_FOR_CODE.get(code, 500)
    if status == 500:
        code = "internal_error"
    return HTTPException(status_code=status, detail={"code": code, "message": message or MESSAGES[code]})


def raise_for(exc: BaseException) -> None:
    """Re-raise ``exc`` as the HTTP error of its code (an ``HTTPException`` or an exception without a code as it is)."""
    if isinstance(exc, HTTPException):
        raise exc
    code = refusal_code(exc)
    if code is None:
        raise exc
    if code not in STATUS_FOR_CODE:
        LOGGER.error("unknown sign-in error code %r", code[:64])
        raise http_error("internal_error")
    raise http_error(code)


class IdentityTaken(SignInRefused):
    """Raise from ``UserDirectory.link_identity`` when the identity is bound to another user."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__("identity_mismatch", message)
