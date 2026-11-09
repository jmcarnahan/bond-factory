"""PKCE (RFC 7636), method S256."""

from __future__ import annotations

import base64
import hashlib
import secrets


def new_verifier() -> str:
    return secrets.token_urlsafe(64)


def challenge(verifier: str) -> str:
    """Unpadded urlsafe base64 of the SHA-256 of the verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
