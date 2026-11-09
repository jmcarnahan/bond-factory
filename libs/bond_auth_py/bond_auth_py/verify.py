"""ID token verification behind one seam: ``verify_id_token(token, settings) -> Identity``.

Three tiers, chosen per call in this order:

1. A verifier installed with ``set_verifier``: an object with ``verify(token) -> dict | Identity`` or a callable.
2. The mock, when ``mock_active(settings)``: registered tokens and the literal ``mock:<email>``.
3. firebase-admin (imported lazily): signature, expiry, audience and issuer against Google's keys.
   ``check_revoked`` only with a service-account key; a missing e-mail is ``incomplete``; an unverified e-mail
   raises ``EmailNotVerified``.

``settings.tier == "injected"`` means tier 1 only: no verifier installed raises ``AuthNotConfigured``
(a subclass of ``AuthUnavailable``).
A rejected token is a ``TokenError`` (``malformed``, ``incomplete``, ``expired``, ``invalid``). A network or
certificate-fetch failure is ``AuthUnavailable`` instead: a provider outage must not read as "rejected".
"""

import logging
from dataclasses import dataclass, field

from bond_auth_py.errors import AuthNotConfigured, AuthUnavailable, EmailNotVerified, TokenError
from bond_auth_py.firebase_app import firebase_app, require_firebase_admin, service_account_info
from bond_auth_py.mock import MockIdentities, default_mock, provider_claims, register_default_token
from bond_auth_py.settings import AuthSettings, mock_active

__all__ = [
    "AuthUnavailable", "EmailNotVerified", "Identity", "MockIdentities", "TokenError", "register_mock_token",
    "set_verifier", "verify_id_token",
]

LOGGER = logging.getLogger(__name__)
MAX_TOKEN_CHARS = 8192
_verifier = None


@dataclass(frozen=True)
class Identity:
    uid: str
    email: str
    name: str | None = None
    auth_time: float | None = None
    sign_in_provider: str = "password"
    identities: dict[str, list[str]] = field(default_factory=dict)


def set_verifier(verifier) -> None:
    """Install a verifier (object with ``verify(token)`` or a callable), or ``None`` to remove it. Tests only."""
    global _verifier
    _verifier = verifier


def register_mock_token(*args, **kwargs) -> None:
    """``MockIdentities.register_mock_token`` on the shared default mock."""
    register_default_token(*args, **kwargs)


def _from_installed(token: str) -> dict:
    verify = getattr(_verifier, "verify", None) or _verifier
    result = verify(token)
    if isinstance(result, Identity):
        return {"uid": result.uid, "email": result.email, "name": result.name, "auth_time": result.auth_time,
                "sign_in_provider": result.sign_in_provider, "identities": result.identities}
    return result


_TRANSPORT_NAMES = frozenset({"CertificateFetchError", "TransportError", "RequestException", "Timeout",
                              "ConnectionError", "ConnectTimeout", "ReadTimeout", "HTTPError"})


def is_transport_error(exc: BaseException) -> bool:
    """Network or certificate-fetch failures (not a verdict on the token): OS-level errors, firebase-admin's
    ``CertificateFetchError``, google-auth ``TransportError`` and requests exceptions. Matched by class name so
    neither ``requests`` nor ``google.auth`` has to be imported here."""
    return isinstance(exc, OSError) or any(c.__name__ in _TRANSPORT_NAMES for c in type(exc).__mro__)


def _from_firebase(token: str, settings: AuthSettings) -> dict:
    if not (settings.firebase_project_id or service_account_info(settings)):
        raise AuthNotConfigured("firebase is not configured")
    require_firebase_admin()  # AuthNotConfigured("install bond_auth_py[firebase]") without the extra
    from firebase_admin import auth as fb_auth

    # Revocation needs the admin credential: one extra lookup, only when we can make it.
    extra = {"check_revoked": True} if service_account_info(settings) is not None else {}
    try:
        claims = fb_auth.verify_id_token(token, app=firebase_app(settings), **extra)
    except fb_auth.ExpiredIdTokenError as exc:
        raise TokenError("expired") from exc
    except (fb_auth.InvalidIdTokenError, fb_auth.RevokedIdTokenError, fb_auth.UserDisabledError, ValueError) as exc:
        raise TokenError("invalid") from exc
    except Exception as exc:
        LOGGER.warning("firebase verify_id_token failed: %s", type(exc).__name__)
        if is_transport_error(exc):  # an outage is not a rejected token: the client must not sign the person out
            raise AuthUnavailable("token verification is unavailable") from exc
        raise TokenError("invalid") from exc
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise TokenError("incomplete")
    if not claims.get("email_verified"):
        raise EmailNotVerified()  # an unverified address is just a claim
    return {"uid": claims.get("uid") or claims.get("sub"), "email": email, "name": claims.get("name"),
            "auth_time": claims.get("auth_time"), **provider_claims(claims.get("firebase"))}


def verify_id_token(token: str, settings: AuthSettings, *, mock: MockIdentities | None = None) -> Identity:
    """The verified identity for an ID token, or ``TokenError`` / ``EmailNotVerified`` / ``AuthUnavailable``."""
    token = (token or "").strip()
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise TokenError("malformed")
    if _verifier is not None:
        result = _from_installed(token)
    elif settings.tier == "injected":
        raise AuthNotConfigured("no verifier installed")
    elif mock_active(settings):
        result = (mock or default_mock()).verify(token)
    else:
        result = _from_firebase(token, settings)
    if not isinstance(result, dict) or not result.get("uid") or not (result.get("email") or "").strip():
        raise TokenError("incomplete")
    auth_time = result.get("auth_time")
    extra = provider_claims({"sign_in_provider": result.get("sign_in_provider"),
                             "identities": result.get("identities")})
    return Identity(uid=str(result["uid"]), email=result["email"].strip().lower(), name=result.get("name"),
                    auth_time=float(auth_time) if auth_time is not None else None,
                    sign_in_provider=extra["sign_in_provider"], identities=extra["identities"])
