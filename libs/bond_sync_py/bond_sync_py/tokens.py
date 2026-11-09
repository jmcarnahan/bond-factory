"""Sync tokens: short ES256 JWTs a sync service accepts, and the JWKS that lets it verify them.

The service never sees a password or a session. It fetches the JWKS (public) and checks signature, audience and expiry;
``sub`` is the user id. Time is the real wall clock unless ``now`` is passed. Every setting arrives in a
``SyncTokenSettings``, so this module reads no configuration except through ``from_env``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DEFAULT_KID = "bond-sync-1"
DEFAULT_AUDIENCE = "powersync"
MIN_MINUTES, MAX_MINUTES = 1, 60


class SyncKeyError(Exception):
    """The signing key is missing or unusable. The message never contains key material."""


@dataclass(frozen=True)
class SyncTokenSettings:
    url: str = ""
    private_key: str = field(default="", repr=False)
    private_key_file: str = ""
    kid: str = DEFAULT_KID
    previous_key: str = field(default="", repr=False)
    previous_key_file: str = ""
    previous_kid: str = ""
    audience: str = DEFAULT_AUDIENCE
    minutes: int = 15

    @classmethod
    def from_env(cls, prefix: str = "BOND_SYNC_", env: Mapping[str, str] | None = None) -> SyncTokenSettings:
        """Read ``<prefix>URL``, ``PRIVATE_KEY``, ``PRIVATE_KEY_FILE``, ``KID``, ``PREVIOUS_KEY``, ``PREVIOUS_KEY_FILE``,
        ``PREVIOUS_KID``, ``AUDIENCE`` and ``MINUTES``. An app with older names builds the dataclass itself."""
        source = os.environ if env is None else env

        def get(name: str, default: str = "") -> str:
            return (source.get(prefix + name) or "").strip() or default

        try:
            minutes = int(get("MINUTES", "15"))
        except ValueError:
            minutes = 15
        return cls(
            url=get("URL"),
            private_key=get("PRIVATE_KEY"),
            private_key_file=get("PRIVATE_KEY_FILE"),
            kid=get("KID", DEFAULT_KID),
            previous_key=get("PREVIOUS_KEY"),
            previous_key_file=get("PREVIOUS_KEY_FILE"),
            previous_kid=get("PREVIOUS_KID"),
            audience=get("AUDIENCE", DEFAULT_AUDIENCE),
            minutes=minutes,
        )

    def lifetime_minutes(self) -> int:
        return max(MIN_MINUTES, min(MAX_MINUTES, self.minutes))


@lru_cache(maxsize=8)
def _parse(pem: str, path: str, mtime: float) -> ec.EllipticCurvePrivateKey:
    """Cached per distinct setting and file mtime, so a replaced file is picked up. Failures are raised, never cached."""
    if not pem and path:
        try:
            pem = Path(path).read_text().strip()
        except OSError as exc:
            raise SyncKeyError(f"the key file cannot be read ({exc.strerror or 'error'})") from exc
    if not pem:
        raise SyncKeyError("no signing key is set")
    try:
        private = serialization.load_pem_private_key(pem.encode(), password=None)
    except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
        raise SyncKeyError(f"the signing key is not a readable unencrypted PEM private key ({type(exc).__name__})") from exc
    if not isinstance(private, ec.EllipticCurvePrivateKey) or private.curve.name != "secp256r1":
        raise SyncKeyError("the signing key must be an EC P-256 key (ES256)")
    return private


def load_private_key(pem: str = "", path: str = "") -> ec.EllipticCurvePrivateKey:
    """The EC P-256 private key from inline PEM or a file. Raises ``SyncKeyError``."""
    mtime = 0.0
    if not pem and path:
        try:
            mtime = Path(path).stat().st_mtime
        except OSError:
            mtime = 0.0
    return _parse(pem, path, mtime)


def clear_cache() -> None:
    _parse.cache_clear()


def key_reason(settings: SyncTokenSettings) -> str:
    """Why the signing key is unusable, or an empty string when it is fine."""
    try:
        load_private_key(settings.private_key, settings.private_key_file)
    except SyncKeyError as exc:
        return str(exc)
    return ""


def is_configured(settings: SyncTokenSettings) -> bool:
    """Sync is on when an endpoint URL and a usable signing key are set."""
    return bool(settings.url) and not key_reason(settings)


def mint_sync_token(settings: SyncTokenSettings, user_id: str, *, now: datetime | None = None) -> tuple[str, datetime]:
    """``(token, expires_at)`` for ``user_id``; ``expires_at`` is naive UTC. Lifetime is clamped to 1-60 minutes."""
    private = load_private_key(settings.private_key, settings.private_key_file)
    issued = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    expires = issued + timedelta(minutes=settings.lifetime_minutes())
    claims = {"sub": user_id, "aud": settings.audience, "iat": int(issued.timestamp()), "exp": int(expires.timestamp())}
    token = jwt.encode(claims, private, algorithm="ES256", headers={"kid": settings.kid})
    return token, expires.replace(tzinfo=None)


def _jwk(private: ec.EllipticCurvePrivateKey, kid: str) -> dict:
    jwk = dict(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key(), as_dict=True))
    jwk.update({"kid": kid, "alg": "ES256", "use": "sig"})
    return jwk


def previous_reason(settings: SyncTokenSettings) -> str:
    """Why a configured previous key is NOT published (empty when none is configured or it is fine)."""
    if not (settings.previous_key or settings.previous_key_file):
        return ""
    if not settings.previous_kid:
        return "the previous kid is not set"
    if settings.previous_kid == settings.kid:
        return "the previous kid equals the current kid"
    try:
        load_private_key(settings.previous_key, settings.previous_key_file)
    except SyncKeyError as exc:
        return str(exc)
    return ""


def jwks(settings: SyncTokenSettings) -> dict:
    """The public JWK set: the current key, and the previous one while a rotation is in progress. Raises ``SyncKeyError``
    when the current key is unusable. A previous key without a usable, distinct kid is ignored."""
    keys = [_jwk(load_private_key(settings.private_key, settings.private_key_file), settings.kid)]
    if (settings.previous_key or settings.previous_key_file) and not previous_reason(settings):
        previous = load_private_key(settings.previous_key, settings.previous_key_file)
        keys.append(_jwk(previous, settings.previous_kid))
    return {"keys": keys}
