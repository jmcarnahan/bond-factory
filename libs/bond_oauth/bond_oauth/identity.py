"""Who signed in: claims read from the ``id_token`` of a code exchange.

No signature check (design decision D13, OIDC Core 3.1.3.7 step 6): the token must have come straight from the
provider's token endpoint over TLS. Never pass a token that arrived any other way (a redirect, a client, a header).
A JWKS check is a named follow-up. What IS checked: three segments, ``alg`` is not ``none`` (except for a provider
that sets ``unsigned_ids_ok``, only ``FakeOAuth``), ``iss``, ``aud``, ``exp``, ``nonce`` and, for Microsoft, the
tenant. Nothing here logs a token.
"""

from __future__ import annotations

import base64
import hmac
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any

from bond_oauth.errors import OAuthError
from bond_oauth.providers import TokenSet

GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
FAKE_ISSUER = "https://fake.invalid"


@dataclass(frozen=True)
class OidcIdentity:
    provider: str
    subject: str  # Google ``sub``; Microsoft ``<tid>:<oid>``. The only stable key: e-mail is a hint, never authority.
    tenant: str | None  # Microsoft ``tid``; None for Google
    email: str  # lowercase, stripped; "" when the provider gave none
    email_verified: bool
    name: str | None
    auth_time: float  # epoch seconds: the ``auth_time`` claim, else the time of this call
    hd: str | None  # Google hosted domain
    raw_claims: dict[str, Any] = field(default_factory=dict, repr=False)


def _bad(message: str = "The sign-in answer carried no valid identity") -> OAuthError:
    return OAuthError("invalid_id_token", message)


def _segment(text: str) -> dict[str, Any]:
    try:
        value = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
    except (ValueError, TypeError):
        raise _bad() from None
    if not isinstance(value, dict):
        raise _bad()
    return value


def _is_microsoft(provider_name: str) -> bool:
    return "microsoft" in provider_name.lower()


def _claims(provider_name: str, provider: Any, tokens: TokenSet, *, expected_nonce: str | None,
            client_id: str | None, now: float) -> dict[str, Any]:
    token = tokens.raw.get("id_token") if isinstance(tokens.raw, dict) else None
    if not token or not isinstance(token, str):
        raise _bad("The provider sent no identity token")
    parts = token.split(".")
    if len(parts) != 3:
        raise _bad()
    header, claims = _segment(parts[0]), _segment(parts[1])
    unsigned_ok = bool(getattr(provider, "unsigned_ids_ok", False))
    if str(header.get("alg", "")).lower() == "none" and not unsigned_ok:
        raise _bad("The identity token is unsigned")
    issuer = claims.get("iss")
    if _is_microsoft(provider_name):
        tid = claims.get("tid")
        allowed = (f"https://login.microsoftonline.com/{tid}/v2.0",) if isinstance(tid, str) and tid else ()
    else:
        allowed = GOOGLE_ISSUERS
    if unsigned_ok:
        allowed += (FAKE_ISSUER,)
    if not isinstance(issuer, str) or issuer not in allowed:
        raise _bad()
    audience = claims.get("aud")
    if client_id is not None and client_id not in (audience if isinstance(audience, list) else [audience]):
        raise _bad()
    try:
        expires = float(claims["exp"])
    except (KeyError, TypeError, ValueError):
        raise _bad() from None
    if not math.isfinite(expires) or expires <= now:
        raise _bad("The identity token has expired")
    if expected_nonce is not None and not hmac.compare_digest(str(claims.get("nonce") or "").encode(),
                                                                 expected_nonce.encode()):
        raise _bad()
    return claims


def _microsoft_subject(claims: dict[str, Any]) -> str:
    tid, oid = claims.get("tid"), claims.get("oid")
    if not (isinstance(tid, str) and tid and isinstance(oid, str) and oid):
        raise _bad()
    return f"{tid}:{oid}"


def _is_guest(claims: dict[str, Any], info: dict[str, Any], tenant: str) -> bool:
    """A guest (B2B) account of the pinned tenant is not a member. Refused when: the id_token ``idtyp`` is
    ``guest``; the sign-in name or the /me ``upn`` contains ``#EXT#``; /me ``user_type`` is ``Guest``; or the
    id_token ``idp`` claim is present and is neither ``https://sts.windows.net/<tid>/`` nor the issuer itself (a
    guest signs in at its home identity provider, which ``idp`` then names)."""
    names = (str(claims.get("preferred_username") or ""), str(info.get("upn") or ""))
    idp = claims.get("idp")
    home = (f"https://sts.windows.net/{tenant}/", f"https://login.microsoftonline.com/{tenant}/v2.0")
    return (str(claims.get("idtyp", "")).lower() == "guest" or any("#ext#" in n.lower() for n in names)
            or str(info.get("user_type") or "").lower() == "guest" or (idp is not None and idp not in home))


def _text(*values: Any) -> str:
    """The first non-empty value that really is a string; a list or number is treated as missing, not coerced."""
    return next((v for v in values if isinstance(v, str) and v.strip()), "")


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def identity_from_token_response(provider_name: str, provider: Any, tokens: TokenSet, *,
                                 expected_nonce: str | None, client_id: str, userinfo: dict | None = None,
                                 now: float | None = None, pinned_tenant: str | None = None) -> OidcIdentity:
    """The signed-in person from a code exchange's ``tokens.raw["id_token"]``.

    ONLY for tokens received directly from the token endpoint over TLS: the signature is not checked (D13).
    ``pinned_tenant`` (else ``provider.pinned_tenant``) is the one Microsoft tenant id to accept; any other ``tid``
    and any guest account raise ``OAuthError("tenant_mismatch")``. Other failures raise
    ``OAuthError("invalid_id_token")``. ``userinfo`` (Microsoft ``/me``) supplies ``mail``, ``upn`` and ``user_type``.
    The Microsoft e-mail is /me ``mail`` first, then the id_token ``email``, then ``preferred_username``: the invite
    holds the mailbox address, which ``mail`` is, while the sign-in name can differ from it.
    """
    stamp = time.time() if now is None else now
    claims = _claims(provider_name, provider, tokens, expected_nonce=expected_nonce, client_id=client_id, now=stamp)
    info = userinfo or {}
    name = claims.get("name") or info.get("name")
    auth_time = claims.get("auth_time")
    when = float(auth_time) if isinstance(auth_time, int | float) and not isinstance(auth_time, bool) else stamp
    if _is_microsoft(provider_name):
        subject = _microsoft_subject(claims)
        tenant = str(claims["tid"])
        pin = pinned_tenant or getattr(provider, "pinned_tenant", None)
        upn = str(claims.get("preferred_username") or "")
        if (pin and tenant.lower() != str(pin).lower()) or _is_guest(claims, info, tenant):
            raise OAuthError("tenant_mismatch", "That account is not from the allowed organisation")
        # The invite holds the mailbox address, so /me ``mail`` wins; the sign-in name is a last resort.
        email = _text(info.get("mail"), claims.get("email"), upn)
        verified, hosted = bool(pin), None  # a pinned work tenant's addresses are owned by its directory
    else:
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub:
            raise _bad()
        subject, tenant = sub, None
        email = _text(claims.get("email"))
        verified = _truthy(claims.get("email_verified"))
        hosted = claims.get("hd") or None
    return OidcIdentity(provider=provider_name, subject=subject, tenant=tenant, email=email.strip().lower(),
                        email_verified=verified, name=str(name) if name else None, auth_time=when,
                        hd=str(hosted) if hosted else None, raw_claims=claims)


def ensure_subject(provider_name: str, provider: Any, tokens: TokenSet, userinfo: dict | None, expected: str) -> None:
    """Connect-flow account binding: ``OAuthError("account_mismatch")`` unless the account that just consented has
    the identity subject ``expected`` (what sign-in bound for this user). Same trust rule as the function above (the
    token came from the exchange); ``aud`` is not compared here. Without an id_token the userinfo ``sub`` or ``id``
    is used (a Microsoft ``id`` is the ``oid`` half of ``<tid>:<oid>``). Fails closed when no subject can be found."""
    found: str | None = None
    if tokens.raw.get("id_token"):
        try:
            claims = _claims(provider_name, provider, tokens, expected_nonce=None, client_id=None, now=time.time())
            found = _microsoft_subject(claims) if _is_microsoft(provider_name) else str(claims.get("sub") or "")
        except OAuthError:
            found = None
    else:
        info = userinfo or {}
        found = str(info.get("sub") or info.get("id") or "") or None
        if found and _is_microsoft(provider_name) and ":" in expected and ":" not in found:
            found = f"{expected.split(':', 1)[0]}:{found}"
    if not found or not hmac.compare_digest(found.encode(), expected.encode()):
        raise OAuthError("account_mismatch", "That is not the account you signed in with")
