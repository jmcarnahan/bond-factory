"""The app's own session JWT (HS256) and how a request carries it.

Claims: ``sub`` and ``user_id`` (both the user id, both required on decode), ``name``, ``capabilities``
(informational: authority is re-read from the database per request), ``iat`` (float epoch, REAL clock: it is
compared with ``sessions_valid_after`` at microsecond precision), ``exp``, ``aud`` (a list) and ``iss``.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import jwt

from bond_auth_py.errors import TokenError
from bond_auth_py.settings import AuthSettings

ALGORITHM = "HS256"
#: Clock difference tolerated between the node that minted a token and the one that checks it (``iat``/``exp``).
#: The revocation comparison against ``sessions_valid_after`` stays exact.
CLOCK_LEEWAY_SECONDS = 10
RESERVED = ("sub", "user_id", "name", "capabilities", "iat", "exp", "aud", "iss")


@dataclass(frozen=True)
class Claims:
    sub: str
    user_id: str
    name: str | None
    capabilities: list[str]
    iat: float
    exp: float
    extra: dict = field(default_factory=dict)


def create_access_token(*, sub: str, name: str | None, capabilities: list[str], settings: AuthSettings,
                        extra_claims: dict | None = None, now: datetime | None = None,
                        ttl: timedelta | None = None) -> str:
    """Mint a session JWT. ``now`` (aware) is for tests; it defaults to the real clock. ``ttl`` overrides
    ``settings.access_ttl_minutes``. ``extra_claims`` may not override the standard ones."""
    if not (settings.jwt_secret or "").strip():
        raise TokenError("misconfigured")  # never sign with an empty key
    issued = now or datetime.now(UTC)
    claims = {k: v for k, v in (extra_claims or {}).items() if k not in RESERVED}
    claims.update({
        "sub": sub, "user_id": sub, "name": name, "capabilities": list(capabilities),
        "iat": issued.timestamp(),
        "exp": issued + (ttl if ttl is not None else timedelta(minutes=settings.access_ttl_minutes)),
        "aud": [settings.audience], "iss": settings.issuer,
    })
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_claims(token: str, settings: AuthSettings) -> Claims:
    """Verify signature, expiry, audience and issuer. No database access. ``TokenError`` otherwise
    (reason ``misconfigured`` when the secret is empty)."""
    if not (settings.jwt_secret or "").strip():
        raise TokenError("misconfigured")  # an empty key must never verify anything
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], audience=[settings.audience],
                             issuer=settings.issuer, leeway=CLOCK_LEEWAY_SECONDS,
                             options={"require": ["exp", "iat"]})
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("expired") from exc
    except (jwt.InvalidTokenError, jwt.InvalidKeyError, TypeError, ValueError) as exc:
        raise TokenError("invalid") from exc
    if not payload.get("sub") or not payload.get("user_id"):
        raise TokenError("incomplete")
    try:
        iat, exp = float(payload["iat"]), float(payload["exp"])
    except (TypeError, ValueError) as exc:
        raise TokenError("invalid") from exc
    extra = {k: v for k, v in payload.items() if k not in RESERVED}
    return Claims(sub=str(payload["sub"]), user_id=str(payload["user_id"]), name=payload.get("name"),
                  capabilities=list(payload.get("capabilities") or []), iat=iat, exp=exp, extra=extra)


def cookie_name(app: str) -> str:
    """``<app>_access_token``: namespaced so two apps on localhost never share a cookie."""
    return f"{app}_access_token"


def session_cookie_params(settings: AuthSettings, *, secure: bool) -> dict:
    """Keyword arguments for ``response.set_cookie`` (HttpOnly, SameSite=Lax, lives as long as the token)."""
    return {"httponly": True, "secure": secure, "samesite": "lax", "path": "/",
            "max_age": settings.access_ttl_minutes * 60}


def read_bearer_or_cookie(request_headers: Mapping[str, str], cookies: Mapping[str, str] | None,
                          cookie: str) -> str | None:
    """The ``Authorization: Bearer`` token first (explicit beats ambient: a stale cookie never overrides it),
    then the named cookie. ``None`` when neither carries a token."""
    for key, value in request_headers.items():
        if key.lower() == "authorization":
            scheme, _, rest = (value or "").strip().partition(" ")
            if scheme.lower() == "bearer" and rest.strip():
                return rest.strip()
            break
    return ((cookies or {}).get(cookie) or "").strip() or None
