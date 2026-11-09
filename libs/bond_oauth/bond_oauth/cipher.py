"""Fernet encryption for stored tokens and the stateless OAuth state.

One master secret yields two independent subkeys with HKDF-SHA256 (``info`` ``bond_oauth/tokens`` and
``bond_oauth/state``), so a state blob never decrypts as a token and the other way round. The secret may be a
Fernet key or any other string; outside throwaway setups use 32 or more random bytes:
``python -c "import secrets; print(secrets.token_urlsafe(32))"``.
"""

from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

TOKENS_INFO = b"bond_oauth/tokens"
STATE_INFO = b"bond_oauth/state"


def _subkey(secret: str, info: bytes) -> Fernet:
    raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(secret.encode())
    return Fernet(base64.urlsafe_b64encode(raw))


def _open(fernet: Fernet, text: str) -> str:
    try:
        return fernet.decrypt((text or "").encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        raise ValueError("cannot be decrypted (wrong key, wrong purpose or damaged text)") from exc


class TokenCipher:
    """``encrypt`` / ``decrypt`` stored tokens; ``encrypt_state`` / ``decrypt_state`` for the OAuth state.

    A wrong key, a blob of the other purpose or damaged text raises ``ValueError``.
    """

    def __init__(self, key: str) -> None:
        if not key or not key.strip():
            raise ValueError("an empty cipher key is not allowed")
        secret = key.strip()
        self._tokens = _subkey(secret, TOKENS_INFO)
        self._state = _subkey(secret, STATE_INFO)

    @classmethod
    def from_env(cls, name: str = "BOND_OAUTH_KEY") -> TokenCipher:
        value = os.environ.get(name, "")
        if not value.strip():
            raise ValueError(f"{name} is not set")
        return cls(value)

    @staticmethod
    def generate_key() -> str:
        return Fernet.generate_key().decode()

    def encrypt(self, plain: str) -> str:
        return self._tokens.encrypt(plain.encode()).decode()

    def decrypt(self, cipher_text: str) -> str:
        return _open(self._tokens, cipher_text)

    def encrypt_state(self, plain: str) -> str:
        return self._state.encrypt(plain.encode()).decode()

    def decrypt_state(self, cipher_text: str) -> str:
        return _open(self._state, cipher_text)
